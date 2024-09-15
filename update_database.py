import asyncio
import base64
import logging
import os
import sys
import time
from datetime import timedelta, datetime

import aiohttp
import durationpy
import reflex as rx
from docker_registry_client_async import ImageName, DockerRegistryClientAsync
from sqlalchemy.sql import text

import database_update.dockerhub_scraper as dockerhub_scraper
from docker_tag_monitor.models import ImageToScrape, ImageUpdate

logger = logging.getLogger("DatabaseUpdater")


async def update_popular_images_to_scrape():
    popular_images = await dockerhub_scraper.get_popular_images()
    if not popular_images:
        return

    images_to_scrape = await dockerhub_scraper.get_images_with_tags_to_scrape(popular_images)
    if not images_to_scrape:
        return

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
                except Exception as e:
                    logging.warning(f"Failed to add image to scrape: {e}")


async def refresh_digests():
    """
    Iterates over all ImageToScrape entries and refreshes the digest for each one.
    """
    logger.info("Refreshing digests for all images")
    # TODO: integrate BackgroundJobExecution
    async with DockerRegistryClientAsync() as registry_client:
        await configure_dockerhub_credentials_if_provided(registry_client)
        with rx.session() as session:
            query = ImageToScrape.select()
            for image_to_scrape in session.exec(query):
                image_name = ImageName.parse(
                    f"{image_to_scrape.endpoint}/{image_to_scrape.image}:{image_to_scrape.tag}")

                try:
                    result = await registry_client.head_manifest(image_name)
                except aiohttp.ClientError as e:
                    # TODO: this needs further investigation - e.g. is this where rate limits would come into play?
                    logging.warning(f"Failed to refresh digest for image '{image_name}': {e}")
                    continue

                digest_was_found_in_registry = result.result
                if digest_was_found_in_registry is True:
                    # Add an entry in the database, if the digest of the most recent one is different (or missing)
                    query = ImageUpdate.select().where(ImageUpdate.image_id == image_to_scrape.id).order_by(
                        ImageUpdate.scraped_at.desc())
                    last_update = session.exec(query).first()
                    if last_update is None or last_update.digest != result.digest:
                        image_update = ImageUpdate(scraped_at=datetime.now(), image_id=image_to_scrape.id,
                                                   digest=result.digest)
                        try:
                            session.add(image_update)
                            session.commit()
                        except Exception as e:
                            logging.warning(f"Failed to add image scrape update for {image_update}: {e}")
                else:
                    logger.warning(f"Failed to refresh digest for image '{image_name}', image/tag not found "
                                   "in registry!")

    logger.info("Digest refresh completed")  # TODO improve logging


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
