import logging
import os
from typing import Optional

import aiohttp
from aiohttp import ClientSession
from docker_registry_client_async import Indices
from pydantic.v1.datetime_parse import parse_datetime
from datetime import datetime

from docker_tag_monitor.constants import DOCKERHUB_IMAGE_QUERY_URL, DOCKERHUB_LIST_TAGS_FOR_IMAGE_URL, \
    DOCKERHUB_TAG_DETAILS_FOR_IMAGE_URL, DOCKERHUB_AUTH_TOKEN_URL
from docker_tag_monitor.models import ImageToScrape

logger = logging.getLogger("DockerHubScraper")

TAGS_PER_IMAGE_MAX_COUNT = 25


async def get_popular_images():
    logger.info("Getting popular images")
    most_popular_images: list[str] = []

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(DOCKERHUB_IMAGE_QUERY_URL, raise_for_status=True) as response:
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
            tags_url = DOCKERHUB_LIST_TAGS_FOR_IMAGE_URL.format(image_name=image_name,
                                                                tags_per_image=TAGS_PER_IMAGE_MAX_COUNT)
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
                if "content_type" in result and result["content_type"] == "image" and "name" in result \
                        and "tag_last_pushed" in result:
                    tag_name = result["name"]
                    last_pushed = result["tag_last_pushed"]  # example: "2025-08-14T12:52:58.11151Z"
                    last_pushed_date: datetime = parse_datetime(last_pushed)
                    images_to_scrape.append(ImageToScrape(endpoint=Indices.DOCKERHUB, image=image_name, tag=tag_name,
                                                          last_updated=last_pushed_date))

    logger.info(f"Retrieved {len(images_to_scrape)} images with tags to scrape")

    return images_to_scrape


async def get_last_push_date(image: ImageToScrape, session: ClientSession) -> Optional[datetime]:
    namespace_name, _, image_name = image.image.partition('/')
    tag_details_url = DOCKERHUB_TAG_DETAILS_FOR_IMAGE_URL.format(namespace_name=namespace_name, image_name=image_name,
                                                                 tag_name=image.tag)
    try:
        async with session.get(tag_details_url, raise_for_status=True) as response:
            tag_details = await response.json()
    except aiohttp.ClientError as e:
        logger.warning(f"Failed to get tag details for image '{image_name}': {e}")
        return None

    if not isinstance(tag_details, dict) or "tag_last_pushed" not in tag_details:
        logger.warning(f"Unexpected response from DockerHub API for tag details of image '{image_name}': {tag_details}")
        return None

    last_pushed = tag_details["tag_last_pushed"]  # example: "2025-08-14T12:52:58.11151Z"
    last_pushed_date: datetime = parse_datetime(last_pushed)
    return last_pushed_date


async def get_dockerhub_auth_header() -> dict[str, str]:
    auth_headers = dict()
    username = os.getenv("DOCKERHUB_USERNAME")
    password = os.getenv("DOCKERHUB_PASSWORD")

    if username and password:
        # See https://docs.docker.com/reference/api/hub/latest/#tag/authentication-api/operation/AuthCreateAccessToken
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    "identifier": username,
                    "secret": password
                }
                async with session.post(DOCKERHUB_AUTH_TOKEN_URL, json=data, raise_for_status=True) as response:
                    result = await response.json()
                    access_token = result["access_token"]
                    auth_headers["Authorization"] = f"Bearer {access_token}"
        except Exception as e:
            logger.warning(f"Failed to authenticate with provided DockerHub username/password: {e}")

    return auth_headers
