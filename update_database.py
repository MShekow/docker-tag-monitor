import asyncio
import logging
import os
import sys
import time
from datetime import timedelta, datetime
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

import aiohttp
import durationpy
import reflex as rx
from asynciolimiter import Limiter
from docker_registry_client_async import ImageName, DockerRegistryClientAsync
from docker_registry_client_async.typing import DockerRegistryClientAsyncHeadManifest
from sqlalchemy.sql import text
from sqlmodel import delete, select, func

import database_update.dockerhub_scraper as dockerhub_scraper
from docker_tag_monitor.models import ImageToScrape, ImageUpdate, BackgroundJobExecution, ScrapedImage
from docker_tag_monitor.utils import get_all_image_tags, configure_client

logger = logging.getLogger("DatabaseUpdater")

http_request_limiter = Limiter(10)  # Note: the value is overwritten in main()


async def update_popular_images_to_scrape():
    popular_images = await dockerhub_scraper.get_popular_images()
    if not popular_images:
        return

    images_to_scrape = await dockerhub_scraper.get_images_with_tags_to_scrape(popular_images)
    if not images_to_scrape:
        return

    new_images = 0

    with rx.session() as session:
        for image_to_scrape in images_to_scrape:
            query = ImageToScrape.select().where(ImageToScrape.endpoint == image_to_scrape.endpoint,
                                                 ImageToScrape.image == image_to_scrape.image,
                                                 ImageToScrape.tag == image_to_scrape.tag)
            database_object = session.exec(query).first()
            if database_object is None:
                try:
                    session.add(image_to_scrape)
                    session.commit()
                    new_images += 1
                except Exception as e:
                    logger.warning(f"Failed to add image to scrape: {e}")

    logger.info(f"Added {new_images} NEW images to scrape to the database")


async def refresh_digests(digest_refresh_cooldown_interval: timedelta):
    """
    Iterates over all ImageToScrape entries and refreshes the digest for each one. Uses batching to speed up the
    process.
    """
    logger.info("Refreshing digests for all images")
    job_execution = BackgroundJobExecution(started=datetime.now(ZoneInfo('UTC')), successful_queries=0,
                                           failed_queries=0)
    async with DockerRegistryClientAsync() as registry_client:
        await configure_client(registry_client)
        with rx.session() as session:
            query = ImageToScrape.select()
            images_to_scrape = []

            async def reset_registry_tokens_and_repeat_query_if_tokens_expired(
                    results: list[Tuple[ImageToScrape, Optional[DockerRegistryClientAsyncHeadManifest]]]):
                result_indices_with_invalid_token = []
                for i, res_tuple in enumerate(results):
                    _img_to_scrape, res = res_tuple
                    if res is not None and not res.result and res.client_response.status == 401:
                        result_indices_with_invalid_token.append(i)
                if result_indices_with_invalid_token:
                    registry_client.tokens.clear()  # force registry_client to re-generate tokens
                    for i in result_indices_with_invalid_token:
                        results[i] = await fetch_digest(results[i][0])
                        img_to_scrape = results[i][0]
                        refetched_result = results[i][1]
                        if refetched_result and not refetched_result.result:
                            logger.warning(
                                f"Failed to refresh digest (due to invalid auth token) for image "
                                f"'{img_to_scrape.endpoint}/{img_to_scrape.image}:{img_to_scrape.tag}'; "
                                f"Status code={refetched_result.client_response.status}; "
                                f"headers={refetched_result.client_response.headers}")

            async def repeat_query_on_hitting_rate_limit(
                    results: list[Tuple[ImageToScrape, Optional[DockerRegistryClientAsyncHeadManifest]]]):
                result_indices_indicating_rate_limit = []
                for i, res_tuple in enumerate(results):
                    _img_to_scrape, res = res_tuple
                    if res is not None and res.client_response.status == 429:
                        result_indices_indicating_rate_limit.append(i)

                if result_indices_indicating_rate_limit:
                    await asyncio.sleep(digest_refresh_cooldown_interval.total_seconds())
                    registry_client.tokens.clear()  # force re-generation of tokens, they likely expired after waiting
                    for i in result_indices_indicating_rate_limit:
                        results[i] = await fetch_digest(results[i][0])
                        img_to_scrape = results[i][0]
                        refetched_result = results[i][1]
                        if refetched_result and not refetched_result.result:
                            logger.warning(
                                f"Failed to refresh digest (due to rate limit) for image "
                                f"'{img_to_scrape.endpoint}/{img_to_scrape.image}:{img_to_scrape.tag}'; "
                                f"Status code={refetched_result.client_response.status}; "
                                f"headers={refetched_result.client_response.headers}")

            async def fetch_digest(img_to_scrape: ImageToScrape) \
                    -> Tuple[ImageToScrape, Optional[DockerRegistryClientAsyncHeadManifest]]:
                image_name = ImageName.parse(
                    f"{img_to_scrape.endpoint}/{img_to_scrape.image}:{img_to_scrape.tag}")
                try:
                    result = await http_request_limiter.wrap(registry_client.head_manifest(image_name))
                    return img_to_scrape, result
                except aiohttp.ClientError as e:
                    if isinstance(e, aiohttp.ServerDisconnectedError | aiohttp.ServerTimeoutError):
                        try:
                            result = await registry_client.head_manifest(image_name)
                            return img_to_scrape, result
                        except aiohttp.ClientError as e:
                            logger.warning(f"Failed to retrieve digest (retried for Server Disconnected "
                                           f"error or Timeout error) for image '{image_name}': {e}")
                    else:
                        logger.warning(f"Failed to retrieve digest for image '{image_name}': {e}")
                    return img_to_scrape, None

            async def update_database_entries(
                    results: list[Tuple[ImageToScrape, Optional[DockerRegistryClientAsyncHeadManifest]]]):
                for img_to_scrape, result in results:
                    if result is None:
                        job_execution.failed_queries += 1
                        continue

                    digest_was_found_in_registry = result.result
                    if digest_was_found_in_registry:
                        query = ImageUpdate.select().where(ImageUpdate.image_id == img_to_scrape.id).order_by(
                            ImageUpdate.scraped_at.desc())
                        last_update = session.exec(query).first()
                        if last_update is None or last_update.digest != result.digest:
                            image_update = ImageUpdate(image_id=img_to_scrape.id, digest=result.digest)
                            try:
                                session.add(image_update)
                                session.commit()
                                job_execution.successful_queries += 1
                            except Exception as e:
                                job_execution.failed_queries += 1
                                logger.warning(f"Failed to add image scrape update for {image_update}: {e}")
                        else:
                            job_execution.successful_queries += 1
                    else:
                        job_execution.failed_queries += 1
                        image_not_found_in_registry = result.client_response.status == 404
                        if image_not_found_in_registry:
                            try:
                                session.delete(img_to_scrape)
                                session.commit()
                                logger.info(f"Deleted ImageToScrape "
                                            f"'{img_to_scrape.endpoint}/{img_to_scrape.image}:{img_to_scrape.tag}' "
                                            f"because it is no longer found in the registry")
                            except Exception as e:
                                logger.warning(f"Unable to delete ImageToScrape "
                                               f"'{img_to_scrape.endpoint}/{img_to_scrape.image}:{img_to_scrape.tag}' "
                                               f"from the registry (image is no longer found in the registry): {e}")
                        else:
                            logger.warning(
                                f"Failed to retrieve digest for image "
                                f"'{img_to_scrape.endpoint}/{img_to_scrape.image}:{img_to_scrape.tag}'; "
                                f"Unexpected status code={result.client_response.status}; "
                                f"headers={result.client_response.headers}")

            batch_size = 10
            for image_to_scrape in session.exec(query):
                images_to_scrape.append(image_to_scrape)
                if len(images_to_scrape) == batch_size:
                    results = await asyncio.gather(*(fetch_digest(image) for image in images_to_scrape))
                    await reset_registry_tokens_and_repeat_query_if_tokens_expired(results)
                    await repeat_query_on_hitting_rate_limit(results)
                    await update_database_entries(results)
                    images_to_scrape = []

            if images_to_scrape:  # batch size has not been reached, but there are still some images left to process
                results = await asyncio.gather(*(fetch_digest(image) for image in images_to_scrape))
                await reset_registry_tokens_and_repeat_query_if_tokens_expired(results)
                await repeat_query_on_hitting_rate_limit(results)
                await update_database_entries(results)

            job_execution.completed = datetime.now(ZoneInfo('UTC'))
            try:
                session.add(job_execution)
                session.commit()
                session.refresh(job_execution)  # necessary to be able to access the query counts in the log call below
            except Exception as e:
                logger.warning(f"Failed to add job execution to database: {e}")

    logger.info(f"Digest refresh completed, {job_execution.successful_queries} successful queries, "
                f"{job_execution.failed_queries} failed queries")


async def monitor_new_tags():
    """
    Determines whether new tags exist for each unique image, compared to the last digest refresh run.
    The basic approach is as follows:
    - We maintain a helper table, ScrapedImage, that contains each unique (endpoint, image) pair from the ImageToScrape
      table, along with a known_tags column that contains all tags that we have seen for this image thus far.
    - For each entry in the ScrapedImage table, we retrieve all tags from the registry and compare them to the
      known_tags column. Those tags that are not yet in known_tags are considered "new" tags, and we add them to
      the ImageToScrape table (if they do not already exist there).
    - In each digest refresh run, we update the known_tags column, so that we always have the latest
      information about all known tags for an image.
    """
    logger.info("Checking whether we need to monitor new tags")
    async with DockerRegistryClientAsync() as registry_client:
        await configure_client(registry_client)
        with rx.session() as session:
            # Fill the scraped_image table with missing rows (each row is a unique (endpoint, image) pair from the
            # image_to_scrape table, with an additional known_tags string-array column)
            query = text("""INSERT INTO scraped_image (endpoint, image)
                            SELECT DISTINCT its.endpoint, its.image
                            FROM image_to_scrape its
                                     LEFT JOIN scraped_image si
                                               ON its.endpoint = si.endpoint AND its.image = si.image
                            WHERE si.endpoint IS NULL
                              AND si.image IS NULL;
                         """)
            session.exec(query)
            session.commit()

            updated_images = 0
            updated_tags = 0

            for scraped_image in session.exec(ScrapedImage.select()):
                image_name = ImageName.parse(f"{scraped_image.endpoint}/{scraped_image.image}")
                try:
                    all_tags = await http_request_limiter.wrap(get_all_image_tags(image_name, client=registry_client))
                except Exception as e:
                    logger.warning(f"Failed to retrieve tags for image '{image_name}': {e}")
                    continue
                if scraped_image.known_tags:
                    tags_to_monitor = set(all_tags) - set(scraped_image.known_tags)
                    for tag_to_monitor in tags_to_monitor:
                        # Only add the ImageToScrape if it does not already exist (e.g. added manually by a user).
                        # Otherwise, we would get a SQL unique constraint violation in the ImageToScrape table!
                        existing_query = ImageToScrape.select().where(ImageToScrape.endpoint == scraped_image.endpoint,
                                                                      ImageToScrape.image == scraped_image.image,
                                                                      ImageToScrape.tag == tag_to_monitor)
                        existing_image_to_scrape = session.exec(existing_query).first()
                        if existing_image_to_scrape is None:
                            image_to_scrape = ImageToScrape(endpoint=scraped_image.endpoint, image=scraped_image.image,
                                                            tag=tag_to_monitor)
                            session.add(image_to_scrape)
                            updated_tags += 1

                if scraped_image.known_tags != all_tags:
                    scraped_image.known_tags = all_tags
                    session.add(scraped_image)
                    updated_images += 1

            session.commit()
            logger.info(
                f"Added a total of {updated_tags} new tags for {updated_images} images to the monitoring database")


async def delete_old_images(image_update_max_age: timedelta, image_last_accessed_max_age: timedelta):
    image_update_cutoff_date = datetime.now(ZoneInfo('UTC')) - image_update_max_age
    image_cutoff_date = datetime.now(ZoneInfo('UTC')) - image_last_accessed_max_age
    with rx.session() as session:
        outdated_images_count = session.exec(
            select(func.count()).select_from(ImageToScrape).where(ImageToScrape.last_viewed < image_cutoff_date)).one()
        session.exec(delete(ImageToScrape).where(ImageToScrape.last_viewed < image_cutoff_date))

        outdated_image_updates_count = session.exec(
            select(func.count()).select_from(ImageUpdate).where(
                ImageUpdate.scraped_at < image_update_cutoff_date)).one()
        session.exec(delete(ImageUpdate).where(ImageUpdate.scraped_at < image_update_cutoff_date))

        if outdated_images_count or outdated_image_updates_count:
            logger.info(f"Deleted {outdated_images_count} outdated ImageToScrape entries and "
                        f"{outdated_image_updates_count} outdated ImageUpdate entries")

        session.commit()


def verify_database_connection():
    with rx.session() as session:
        session.exec(text("SELECT 1"))  # raises in case the connection to the DB cannot be established


async def main():
    verify_database_connection()
    last_image_refresh_timestamp = -999999999
    last_digest_refresh_timestamp = -999999999

    image_refresh_interval = durationpy.from_str(os.getenv("IMAGE_REFRESH_INTERVAL", "1d"))
    """
    How often to update the ImageToScrape table with new "popular" images from Docker Hub.
    """
    digest_refresh_interval = durationpy.from_str(os.getenv("DIGEST_REFRESH_INTERVAL", "1h"))
    """
    How often to check for digest changes for all ImageToScrape entries.
    """
    image_update_max_age = durationpy.from_str(os.getenv("IMAGE_UPDATE_MAX_AGE", "1y"))
    """
    Retention period of ImageUpdate entries (entries older than this will be automatically deleted)
    """
    image_last_accessed_max_age = durationpy.from_str(os.getenv("IMAGE_LAST_ACCESSED_MAX_AGE", "2y"))
    """
    Retention period of ImageToScrape entries: entries whose last access is older than this configured interval 
    will be automatically deleted.
    """
    auto_monitor_new_tags = os.getenv("AUTO_MONITOR_NEW_TAGS", "true").lower() in ["true", "1", "yes"]
    """
    Whether to cache all known tags in the database, such that when refreshing digests, we also check whether the
    image maintainers have added new tags since the last scrape, and if so, we monitor these tags automatically.
    """
    digest_refresh_cooldown_interval = durationpy.from_str(os.getenv("DIGEST_REFRESH_COOLDOWN_INTERVAL", "1m"))
    """
    Time interval to wait before repeating requests when hitting the registry's rate limit (getting HTTP 429 status
    codes in the response).
    """
    max_requests_per_second = int(os.getenv("MAX_REQUESTS_PER_SECOND", "10"))
    """
    Maximum number of requests per second made to image registries (to avoid hitting their rate limits).
    """

    global http_request_limiter
    http_request_limiter = Limiter(max_requests_per_second)

    while True:
        now = time.monotonic()
        if (now - last_image_refresh_timestamp) > image_refresh_interval.total_seconds():
            await update_popular_images_to_scrape()
            last_image_refresh_timestamp = time.monotonic()

        now = time.monotonic()
        if (now - last_digest_refresh_timestamp) > digest_refresh_interval.total_seconds():
            await delete_old_images(image_update_max_age, image_last_accessed_max_age)

            if auto_monitor_new_tags:
                await monitor_new_tags()

            digest_refresh_start = time.monotonic()
            await refresh_digests(digest_refresh_cooldown_interval)
            last_digest_refresh_timestamp = time.monotonic()

            digest_refresh_duration = timedelta(seconds=last_digest_refresh_timestamp - digest_refresh_start)
            if digest_refresh_duration > digest_refresh_interval:
                logger.warning(f"Digest refresh took longer than the interval - some optimizations are required "
                               f"(duration: {digest_refresh_duration}")
        else:
            await asyncio.sleep(10)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("SIGINT detected, exiting...")
