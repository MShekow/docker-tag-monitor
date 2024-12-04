import logging
from urllib.parse import quote

import aiohttp
import reflex as rx
from docker_registry_client_async import ImageName, DockerRegistryClientAsync, Indices
from sqlmodel import col

from docker_tag_monitor.constants import DOCKERHUB_LIST_TAGS_FOR_IMAGE_URL
from docker_tag_monitor.models import ImageToScrape

logger = logging.getLogger("DockerTagMonitor-Utils")

TAGS_PER_IMAGE_MAX_COUNT = 50


async def images_exists_in_registry(image_names: list[ImageName]) -> bool:
    async with DockerRegistryClientAsync() as registry_client:
        try:
            for image_name in image_names:
                result = await registry_client.head_manifest(image_name)
                if not result.result:
                    return False
        except Exception as e:
            return False

    return True


async def get_most_recently_pushed_tags(image_name: ImageName, max_count: int,
                                        name_filter: str = "") -> list[str]:
    # Note: while it would be nice to have a glob/fnmatch-like filter, the "/repositories" APIs of registries
    # for which supports_name_filter_in_http_call = True (e.g. Docker Hub) don't support this syntax.
    tags: list[str] = []
    supports_name_filter_in_http_call = False

    if image_name.resolve_endpoint() == Indices.DOCKERHUB:
        supports_name_filter_in_http_call = True
        async with aiohttp.ClientSession() as session:
            # Note: the results are already sorted by tag push date (descending)
            tags_url = DOCKERHUB_LIST_TAGS_FOR_IMAGE_URL.format(image_name=image_name.resolve_image(),
                                                                tags_per_image=max_count)
            if name_filter:
                tags_url += f"&name={quote(name_filter)}"
            try:
                async with session.get(tags_url, raise_for_status=True) as response:
                    results = await response.json()
            except aiohttp.ClientError as e:
                raise ValueError(f"Error calling the Docker Hub endpoint and parsing the response: {e}")

            if not isinstance(results, dict) or "results" not in results:
                logger.warning("Unexpected response structure from DockerHub API, missing results")

            for result in results["results"]:
                if "content_type" in result and result["content_type"] == "image" and "name" in result:
                    version_tag = result["name"]
                    tags.append(version_tag)

    elif image_name.resolve_endpoint() == Indices.QUAY:
        url = "https://quay.io/api/v1/repository/{image}/tag/?limit={max_count}&page=1"
        async with aiohttp.ClientSession() as session:
            # Note: the results are already sorted by tag push date (descending)
            tags_url = url.format(image=image_name.image, max_count=max_count)
            try:
                async with session.get(tags_url, raise_for_status=True) as response:
                    results = await response.json()
            except aiohttp.ClientError as e:
                raise ValueError(f"Error calling the Quay endpoint and parsing the response: {e}")

            if not isinstance(results, dict) or "tags" not in results:
                logger.warning("Unexpected response structure from Quay API, missing tags list")

            for result in results["tags"]:
                if "name" in result:
                    version_tag = result["name"]
                    tags.append(version_tag)

    elif image_name.resolve_endpoint() == "mcr.microsoft.com":
        """
        In MCR, there are two relevant endpoints:

        1) https://mcr.microsoft.com/api/v1/catalog/{image}/details?reg=mar

        Returns a small JSON with some meta-data, together with a list of supported(!) tags (simple string list, no
        information regarding the last push date). This list seems to be sorted by semver (descending), and is
        usually rather small (< 50 items).

        2) https://mcr.microsoft.com/api/v1/catalog/{image}/tags?reg=mar

        Returns a HUGE list of all tags that were ever pushed (including non-supported ones, e.g. dotnet/aspnet:2.1),
        each entry contains detailed information about the tag, such as the name, a "createdDate" or "lastModifiedDate".

        For the sake of simplicity, we chose to just return the list of supported tags from endpoint 1.
        """
        url = "https://mcr.microsoft.com/api/v1/catalog/{image}/details?reg=mar"
        async with aiohttp.ClientSession() as session:
            details_url = url.format(image=image_name.image)
            try:
                async with session.get(details_url, raise_for_status=True) as response:
                    details = await response.json()
            except aiohttp.ClientError as e:
                raise ValueError(f"Error calling the mcr.microsoft.com endpoint and parsing the response: {e}")

        if (not isinstance(details, dict) or "supportedTags" not in details or
                not isinstance(details["supportedTags"], list)):
            raise ValueError("Unexpected response structure from mcr.microsoft.com, missing list of supported tags")

        tags = details["supportedTags"]

    else:
        # Simple fallback solution
        async with DockerRegistryClientAsync() as registry_client:
            """
            Note: we are not doing the paginated calls on purpose
            (which is described here: https://distribution.github.io/distribution/spec/api/#listing-image-tags)
            Typically, the returned tag list will be (VERY) long, can e.g. contain about 1000 tags already on the first
            page. However, sorting this list by push date would be extremely labor-intensive, which is why we
            don't do it.

            If we really wanted to sort the tag list by date, we would have to do the following for every entry in
            tag_list_response.tags:
            - Retrieve the manifest of the tag
            - If the returned manifest is an image INDEX, we choose one of the referenced image MANIFESTS at random and
              retrieve its manifest
            - Retrieve the blob of the "config" object of the manifest, parse the entries in "history" -> "created"
              (see https://github.com/opencontainers/image-spec/blob/main/config.md), and assume that the image was
              pushed immediately after the "created" date (which just indicates when layers where built)
            """
            tag_list_response = await registry_client.get_tag_list(image_name)
            # Note: tag_list_response.tags is an array of ImageName objects
            tag_list: list[ImageName] = tag_list_response.tags
            tags = [tag.tag for tag in tag_list]  # noqa (type parser false positive)

    if not supports_name_filter_in_http_call:
        tags = [t for t in tags if name_filter in t]

    return tags[:max_count]


async def get_additional_image_tags_to_monitor(image_name: ImageName, name_filter: str = "") -> list[tuple[str, bool]]:
    """
    Returns tuples where [0] indicates the tag and [1] is True if the tag can still be added to the monitoring DB,
    False otherwise.
    """
    most_recently_pushed_tags = await get_most_recently_pushed_tags(image_name,
                                                                    max_count=TAGS_PER_IMAGE_MAX_COUNT,
                                                                    name_filter=name_filter)

    # We don't want to search for the tag of `image_name`, because that is the tag whose details page
    # the user currently looks at (so it is obviously already monitored). So we filter it out:
    most_recently_pushed_tags = [tag for tag in most_recently_pushed_tags if tag != image_name.tag]

    with rx.session() as session:
        query = ImageToScrape.select().where(ImageToScrape.endpoint == image_name.endpoint,
                                             ImageToScrape.image == image_name.image,
                                             col(ImageToScrape.tag).in_(most_recently_pushed_tags))
        monitored_images_to_scrape: list[ImageToScrape] = session.exec(query).all()

    monitored_image_tags = set(m.tag for m in monitored_images_to_scrape)

    return [(tag, tag not in monitored_image_tags) for tag in most_recently_pushed_tags]


async def add_selected_tags_to_monitoring_db(image_name: ImageName, selected_tags: list[str]):
    # To prevent that hackers can send manipulated requests to flood the database with invalid tags,
    # we check again that the user-selected tags REALLY exist in the registry
    image_names = [ImageName(endpoint=image_name.endpoint, image=image_name.image, tag=tag) for tag in selected_tags]
    if not await images_exists_in_registry(image_names):
        raise ValueError("Some of the selected images do not exist in the registry")

    try:
        with rx.session() as session:
            images_to_scrape = [ImageToScrape(endpoint=image_name.endpoint, image=image_name.image, tag=tag)
                                for tag in selected_tags]
            session.bulk_save_objects(images_to_scrape)
            session.commit()
    except Exception as e:
        raise ValueError(f"Database insert failed: {e}")

    return True
