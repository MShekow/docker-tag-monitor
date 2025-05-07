import base64
import logging
import os
from typing import Optional

import reflex as rx
from docker_registry_client_async import ImageName, DockerRegistryClientAsync
from sqlmodel import col

from docker_tag_monitor.models import ImageToScrape

logger = logging.getLogger("DockerTagMonitor-Utils")

TAGS_PER_IMAGE_MAX_COUNT = 50


async def configure_client(registry_client: DockerRegistryClientAsync):
    # Add Docker Hub credentials, if provided via environment variables
    username = os.getenv("DOCKERHUB_USERNAME")
    password = os.getenv("DOCKERHUB_PASSWORD")
    # Note: from various experiments, since we just perform HEAD requests to Docker Hub, it seems that there is no
    # ratelimit-related difference between using an account, or being anonymous
    if username and password:
        b64_credentials = base64.b64encode(f"{username}:{password}".encode("ascii")).decode("ascii")
        await registry_client.add_credentials(credentials=b64_credentials, endpoint="https://index.docker.io/")

    # Add compatibility for Chainguard's registry, whose auth endpoint does not return Content-Type: application/json
    # but "text/plain", which causes an exception within the library
    await registry_client.add_auth_token_json_kwargs(
        endpoint="cgr.dev", json_kwargs={"content_type": "text/plain"}
    )


async def images_exists_in_registry(image_names: list[ImageName]) -> bool:
    async with DockerRegistryClientAsync() as registry_client:
        await configure_client(registry_client)
        try:
            for image_name in image_names:
                result = await registry_client.head_manifest(image_name)
                if not result.result:
                    return False
        except Exception as e:
            return False

    return True


async def get_all_image_tags(image_name: ImageName, client: Optional[DockerRegistryClientAsync] = None) -> list[str]:
    close_connection = False
    if client is None:
        client = DockerRegistryClientAsync()
        await configure_client(client)
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
    try:
        tag_list_response = await client.get_tag_list(image_name)
        # Note: tag_list_response.tags is an array of ImageName objects
        tag_list: list[ImageName] = tag_list_response.tags
        tags: list[str] = [tag.tag for tag in tag_list]  # noqa (type parser false positive)
        # Tags are returned in lexicographical order, so usually "oldest version first". To the user, it will be more
        # practical to see the most recent versions first, so we reverse the order
        tags.reverse()

        # Remove tags that point to (Cosign/Notation) signatures or attestations. The naming scheme for such tags is
        # sha256-<64-characters-of-the-hash>[.att|.sig|.sbom]
        def is_signature_or_attestation(t: str) -> bool:
            # 71 = len("sha256-") + 64
            return len(t) >= 71 and t.startswith("sha256-")

        tags = [t for t in tags if not is_signature_or_attestation(t)]

        return tags
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
        query = ImageToScrape.select().where(ImageToScrape.endpoint == image_name.endpoint,
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
