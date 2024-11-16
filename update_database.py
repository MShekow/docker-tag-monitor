import asyncio
import base64
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
from docker_registry_client_async import ImageName, DockerRegistryClientAsync
from docker_registry_client_async.typing import DockerRegistryClientAsyncHeadManifest
from sqlalchemy.sql import text

import database_update.dockerhub_scraper as dockerhub_scraper
from docker_tag_monitor.models import ImageToScrape, ImageUpdate, BackgroundJobExecution

logger = logging.getLogger("DatabaseUpdater")


# TODO: delete ImageToScrape (and ImageUpdate) entries for images that do no longer exist

# TODO: delete ImageUpdate entries that are over a certain age

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
                    logging.warning(f"Failed to add image to scrape: {e}")

    logger.info(f"Added {new_images} NEW images to scrape to the database")


async def refresh_digests():
    """
    Iterates over all ImageToScrape entries and refreshes the digest for each one. Uses batching to speed up the
    process.
    """
    logger.info("Refreshing digests for all images")
    job_execution = BackgroundJobExecution(started=datetime.now(ZoneInfo('UTC')), successful_queries=0,
                                           failed_queries=0)
    async with DockerRegistryClientAsync() as registry_client:
        await configure_dockerhub_credentials_if_provided(registry_client)
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
                    registry_client.tokens.clear()
                    for i in result_indices_with_invalid_token:
                        results[i] = await fetch_digest(results[i][0])
                        img_to_scrape = results[i][0]
                        refetched_result = results[i][1]
                        if refetched_result and refetched_result.client_response.status == 401:
                            logger.warning(
                                f"Failed to refresh digest for image "
                                f"'{img_to_scrape.endpoint}/{img_to_scrape.image}:{img_to_scrape.tag}', client "
                                f"token expired, repeating the query again shortly")

            async def fetch_digest(img_to_scrape: ImageToScrape) \
                    -> Tuple[ImageToScrape, Optional[DockerRegistryClientAsyncHeadManifest]]:
                image_name = ImageName.parse(
                    f"{img_to_scrape.endpoint}/{img_to_scrape.image}:{img_to_scrape.tag}")
                try:
                    result = await registry_client.head_manifest(image_name)
                    return img_to_scrape, result
                except aiohttp.ClientError as e:
                    logging.warning(f"Failed to retrieve digest for image '{image_name}': {e}")
                    return img_to_scrape, None

            async def process_results(
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
                            image_update = ImageUpdate(scraped_at=datetime.now(), image_id=img_to_scrape.id,
                                                       digest=result.digest)
                            try:
                                session.add(image_update)
                                session.commit()
                                job_execution.successful_queries += 1
                            except Exception as e:
                                job_execution.failed_queries += 1
                                logging.warning(f"Failed to add image scrape update for {image_update}: {e}")
                        else:
                            job_execution.successful_queries += 1
                    else:
                        job_execution.failed_queries += 1
                        logger.warning(
                            f"Failed to refresh digest for image "
                            f"'{img_to_scrape.endpoint}/{img_to_scrape.image}:{img_to_scrape.tag}', "
                            f"image/tag not found in registry! Status code={result.client_response.status}; "
                            f"headers={result.client_response.headers}")

            batch_size = 10
            for image_to_scrape in session.exec(query):
                images_to_scrape.append(image_to_scrape)
                if len(images_to_scrape) == batch_size:
                    results = await asyncio.gather(*(fetch_digest(image) for image in images_to_scrape))
                    await reset_registry_tokens_and_repeat_query_if_tokens_expired(results)
                    await process_results(results)
                    images_to_scrape = []

            if images_to_scrape:  # batch size has not been reached, but there are still some images left to process
                results = await asyncio.gather(*(fetch_digest(image) for image in images_to_scrape))
                await reset_registry_tokens_and_repeat_query_if_tokens_expired(results)
                await process_results(results)

            job_execution.completed = datetime.now(ZoneInfo('UTC'))
            try:
                session.add(job_execution)
                session.commit()
                session.refresh(job_execution)  # necessary to be able to access the query counts in the log call below
            except Exception as e:
                logging.warning(f"Failed to add job execution to database: {e}")

    logger.info(f"Digest refresh completed, {job_execution.successful_queries} successful queries, "
                f"{job_execution.failed_queries} failed queries")


async def configure_dockerhub_credentials_if_provided(registry_client: DockerRegistryClientAsync):
    username = os.getenv("DOCKERHUB_USERNAME")
    password = os.getenv("DOCKERHUB_PASSWORD")
    if username and password:
        b64_credentials = base64.b64encode(f"{username}:{password}".encode("ascii")).decode("ascii")
        await registry_client.add_credentials(credentials=b64_credentials, endpoint="https://index.docker.io/")


def verify_database_connection():
    with rx.session() as session:
        session.exec(text("SELECT 1"))  # raises in case the connection to the DB cannot be established


async def main():
    verify_database_connection()
    last_image_refresh_timestamp = -999999999
    last_digest_refresh_timestamp = -999999999

    image_refresh_interval = durationpy.from_str(os.getenv("IMAGE_REFRESH_INTERVAL", "1d"))
    digest_refresh_interval = durationpy.from_str(os.getenv("DIGEST_REFRESH_INTERVAL", "1h"))

    while True:
        now = time.monotonic()
        if (now - last_image_refresh_timestamp) > image_refresh_interval.total_seconds():
            await update_popular_images_to_scrape()
            last_image_refresh_timestamp = time.monotonic()

        now = time.monotonic()
        if (now - last_digest_refresh_timestamp) > digest_refresh_interval.total_seconds():
            await refresh_digests()
            last_digest_refresh_timestamp = time.monotonic()

            digest_refresh_duration = timedelta(seconds=time.monotonic() - now)
            if digest_refresh_duration > digest_refresh_interval:
                logging.warning(f"Digest refresh took longer than the interval - some optimizations are required "
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
