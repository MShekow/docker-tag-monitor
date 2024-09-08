import logging

import aiohttp
from docker_registry_client_async import Indices

from docker_tag_monitor.models import ImageToScrape

POPULAR_IMAGES_MAX_COUNT = 50
TAGS_PER_IMAGE_MAX_COUNT = 25

# URL was reverse engineered (via browser web dev tools) from the page
# https://hub.docker.com/search?type=image&image_filter=official%2Cstore%2Copen_source
IMAGE_QUERY_URL = (f"https://hub.docker.com/api/search/v3/catalog/search?from=0&size={POPULAR_IMAGES_MAX_COUNT}&query="
                   "&type=image&source=store&official=true&open_source=true")
LIST_TAGS_FOR_IMAGE_URL = ("https://hub.docker.com/v2/repositories/{image_name}/tags"
                           f"?page_size={TAGS_PER_IMAGE_MAX_COUNT}&ordering=last_updated")

logger = logging.getLogger("DockerHubScraper")


async def get_popular_images():
    logger.info("Getting popular images")
    most_popular_images: list[str] = []

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(IMAGE_QUERY_URL, raise_for_status=True) as response:
                data = await response.json()
        except aiohttp.ClientError as e:
            logger.warning(f"Failed to get list of popular DockerHub images: {e}")
            return most_popular_images

        if not isinstance(data, dict) or "results" not in data:
            logger.warning(f"Unexpected response from DockerHub API: {data}")
            return most_popular_images

        for result in data["results"]:
            if "id" not in result:
                logger.warning(f"Unexpected result format for a specific result ('id' field is missing): {result}")
                continue

            image_name = result["id"]
            most_popular_images.append(image_name)

    logger.info(f"Retrieved {len(most_popular_images)} popular images")

    return most_popular_images

async def get_images_with_tags_to_scrape(most_popular_images: list[str]) -> list[ImageToScrape]:
    logger.info("Retrieving tags for the popular images")
    images_to_scrape: list[ImageToScrape] = []

    async with aiohttp.ClientSession() as session:
        for image_name in most_popular_images:
            tags_url = LIST_TAGS_FOR_IMAGE_URL.format(image_name=image_name)
            try:
                async with session.get(tags_url, raise_for_status=True) as response:
                    tags = await response.json()
            except aiohttp.ClientError as e:
                logger.warning(f"Failed to get tags for image '{image_name}': {e}")
                return images_to_scrape

            if not isinstance(tags, dict) or "results" not in tags:
                logger.warning(f"Unexpected response from DockerHub API for image '{image_name}': {tags}")
                continue

            for result in tags["results"]:
                if "content_type" in result and result["content_type"] == "image" and "name" in result:
                    tag_name = result["name"]
                    images_to_scrape.append(ImageToScrape(endpoint=Indices.DOCKERHUB, image=image_name, tag=tag_name))

    logger.info(f"Retrieved {len(images_to_scrape)} images with tags to scrape")

    return images_to_scrape
