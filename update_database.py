import asyncio
import base64
import os

import sys

import aiohttp
from docker_registry_client_async import ImageName, DockerRegistryClientAsync

async def get_popular_images():
    async with aiohttp.ClientSession() as session:
        async with session.get("https://hub.docker.com/api/search/v3/catalog/search?from=0&size=50&query=&type=image&source=store&official=true&open_source=true", raise_for_status=True) as response:
            data = await response.json()
            for result in data["results"]:
                image_name = result["id"]
                async with session.get(
                    f"https://hub.docker.com/v2/repositories/{image_name}/tags?page_size=25&ordering=last_updated",
                    raise_for_status=True) as response_inner:
                        tags = await response_inner.json()
                        # iterate over "results", each object should have a "content_type" == "image" field, the version tag is stored in "name" (e.g. "latest")

async def get_digest():
    image_name = ImageName.parse("busybox:1.30.1")
    async with DockerRegistryClientAsync() as drca:
        username = os.getenv("DOCKER_USERNAME")
        password = os.getenv("DOCKER_PASSWORD")
        await drca.add_credentials(credentials=base64.b64encode(f"{username}:{password}".encode("ascii")).decode("ascii"), endpoint="https://index.docker.io/")

        for i in range(100):
            result = await drca.head_manifest(image_name)
            # if result.result is True, see result.digest (str)
            print(result.client_response.headers["ratelimit-limit"])
            print(result.client_response.headers["ratelimit-remaining"])
            # Note: the values for ratelimit-remaining DON'T seem to decrease ...
            print(str(i))
        i = 2

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.get_event_loop()
    loop.run_until_complete(get_popular_images())
