import asyncio
import base64
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import durationpy
import reflex as rx
from aiohttp import ContentTypeError, ClientResponseError
from docker_registry_client_async import ImageName, DockerRegistryClientAsync
from sqlmodel import col, select

from docker_tag_monitor.models import ImageToScrape

logger = logging.getLogger("DockerTagMonitor-Utils")

TAGS_PER_IMAGE_MAX_COUNT = 50


async def configure_and_reset_client(registry_client: DockerRegistryClientAsync):
    # Add Docker Hub credentials, if provided via environment variables
    username = os.getenv("DOCKERHUB_USERNAME")
    password = os.getenv("DOCKERHUB_PASSWORD")
    # Note: from various experiments, since we just perform HEAD requests to Docker Hub, it seems that there is no
    # ratelimit-related difference between using an account, or being anonymous
    if username and password:
        b64_credentials = base64.b64encode(f"{username}:{password}".encode("ascii")).decode("ascii")
        await registry_client.add_credentials(credentials=b64_credentials, endpoint="https://index.docker.io/")

    registry_client.tokens.clear()  # do the reset first, otherwise it would undo the configuration done next
    # Add compatibility for Chainguard's registry, whose auth endpoint does not return Content-Type: application/json
    # but "text/plain", which would cause an aiohttp.ContentTypeError within the docker_registry_client_async library.
    # By setting the value to an empty string, the aiohttp client's json() method WON'T check the content type at all.
    await registry_client.add_auth_token_json_kwargs(
        endpoint="cgr.dev", json_kwargs={"content_type": ""}
    )


async def images_exists_in_registry(image_names: list[ImageName]) -> bool:
    async with DockerRegistryClientAsync() as registry_client:
        await configure_and_reset_client(registry_client)
        try:
            for image_name in image_names:
                result = await registry_client.head_manifest(image_name)
                if not result.result:
                    return False
        except Exception as e:
            return False

    return True


def contains_digest(tag: str, min_segment_length: int = 32) -> bool:
    """
    Detects tags containing long sequences of alphanumeric characters that look like
    digests or hashes (e.g.,
    "update-available-441cc46cf89f0bc773dc84872ccab6c3b4a81dda7b946087b072f613d81ed106", or Notation/Cosign
    "sha256-<64-characters-of-the-hash>[.att|.sig|.sbom]" tags).
    Returns True if the tag contains at least one sequence of `min_length` or more consecutive
    alphanumeric characters.
    """
    # Find all sequences of consecutive alphanumeric characters, e.g., splitting
    # "1.2-update-available-441cc46cf89f0bc773dc84872ccab6c3b4a81dda7b946087b072f613d81ed106" into
    # ["1", "2", "update", "available", "441cc46cf89f0bc773dc84872ccab6c3b4a81dda7b946087b072f613d81ed106"]
    alphanumeric_sequences = re.findall(r'[a-zA-Z0-9]+', tag)
    return any(len(seq) >= min_segment_length for seq in alphanumeric_sequences)


async def get_all_image_tags(image_name: ImageName, client: Optional[DockerRegistryClientAsync] = None) -> list[str]:
    close_connection = False
    if client is None:
        client = DockerRegistryClientAsync()
        await configure_and_reset_client(client)
        close_connection = True
    """
    Ideally, we would like the sorting of the returned tags to be done by push-date (descending).
    An earlier (removed) implementation used the proprietary /repositories API endpoints of specific registries
    (e.g. Docker Hub, Quay, and Microsoft MCR) to achieve this. But these registry endpoints did not support glob-
    like search syntax, and the implementation was complex (see Git commit 6f6027d96a78270220c5bdeb26e8151d92700ec7
    and earlier).

    Instead, we now simply use the official tag list feature that every image registry offers.
    The returned tag list is sorted lexicographically, not by push date, and to achieve the latter, we would have
    to do the following for every entry in tag_list_response.tags (which is too much work / network calls to be
    feasible):
    - Retrieve the manifest of the tag
    - If the returned manifest is an image INDEX, we choose one of the referenced image MANIFESTS at random and
      retrieve its manifest
    - Retrieve the blob of the "config" object of the manifest, parse the entries in "history" -> "created"
      (see https://github.com/opencontainers/image-spec/blob/main/config.md), and assume that the image was
      pushed immediately after the "created" date (which just indicates when layers where built)

    Also, note that we are NOT using paginated calls on purpose (which is described here:
    https://distribution.github.io/distribution/spec/api/#listing-image-tags).
    It seems that registries like Docker Hub and MCR return ALL tags without enforcing pagination, even if an
    image has thousands of tags.
    """
    # TODO implement pagination, because e.g. otherwise the OWASP ZAP image hosted on GHCR will not return all tags
    try:
        max_retries = 5
        custom_content_type_header_value = ""
        last_error: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                json_kwargs = {"content_type": custom_content_type_header_value} if custom_content_type_header_value \
                    else None
                tag_list_response = await client.get_tag_list(image_name, json_kwargs=json_kwargs)
            except ClientResponseError as e:
                if attempt == max_retries - 1:
                    last_error = e
                    break

                if isinstance(e, ContentTypeError) and e.status == 200 and \
                        (content_type := e.headers["content-type"]) != "application/json":
                    custom_content_type_header_value = content_type

                if not custom_content_type_header_value:
                    logger.debug(f"Attempt {attempt + 1}/{max_retries} to get tags for {image_name} failed "
                                 f"with ClientResponseError (trying again ...): {e}")
                await asyncio.sleep(1)

                continue

            # Note: tag_list_response.tags is an array of ImageName objects
            tag_list: list[ImageName] = tag_list_response.tags
            tags: list[str] = [tag.tag for tag in tag_list]  # noqa (type parser false positive)
            # Tags are returned in lexicographical order, so usually "oldest version first". To the user, it will be more
            # practical to see the most recent versions first, so we reverse the order
            tags.reverse()

            tags = [t for t in tags if not contains_digest(t)]

            return tags

        if last_error is not None:
            raise last_error
    finally:
        if close_connection:
            await client.close()


async def get_additional_image_tags_to_monitor(image_name: ImageName, name_filter: str = "") -> list[tuple[str, bool]]:
    """
    Returns tuples where [0] indicates the tag and [1] is True if the tag can still be added to the monitoring DB,
    False otherwise.
    """
    tags = await get_all_image_tags(image_name)

    # We don't want to search for the tag of `image_name`, because that is the tag whose details page
    # the user currently looks at (so it is obviously already monitored). So we filter it out:
    tags = [tag for tag in tags if tag != image_name.tag]

    with rx.session() as session:
        query = select(ImageToScrape).where(ImageToScrape.endpoint == image_name.endpoint,
                                            ImageToScrape.image == image_name.image,
                                            col(ImageToScrape.tag).in_(tags))
        monitored_images_to_scrape: list[ImageToScrape] = session.exec(query).all()  # noqa

    monitored_image_tags = set(m.tag for m in monitored_images_to_scrape)

    return [(tag, tag not in monitored_image_tags) for tag in tags]


async def add_selected_tags_to_monitoring_db(image_name: ImageName, selected_tags: list[str]):
    # To prevent that hackers can send manipulated requests to flood the database with invalid tags,
    # we check again that the user-selected tags REALLY exist in the registry
    image_names = [ImageName(endpoint=image_name.endpoint, image=image_name.image, tag=tag) for tag in selected_tags]
    if not await images_exists_in_registry(image_names):
        raise ValueError("Some of the selected images do not exist in the registry")

    try:
        with rx.session() as session:
            images_to_scrape = [ImageToScrape(endpoint=image_name.endpoint, image=image_name.image, tag=tag)  # noqa
                                for tag in selected_tags]
            session.bulk_save_objects(images_to_scrape)
            session.commit()
    except Exception as e:
        raise ValueError(f"Database insert failed: {e}")

    return True


refresh_digest_last_pushed_cutoff: timedelta = durationpy.from_str(
    os.getenv("REFRESH_DIGEST_LAST_PUSHED_CUTOFF", "6mm"))


def is_image_no_longer_scanned(image: ImageToScrape) -> bool:
    """
    Determines whether an image is considered "no longer scanned" based on its last pushed date
    and the configured cutoff duration.
    """
    if not image.last_pushed:
        return False

    if image.tag == "latest":
        return False

    cutoff_datetime = datetime.now(ZoneInfo('UTC')) - refresh_digest_last_pushed_cutoff
    return image.last_pushed < cutoff_datetime
