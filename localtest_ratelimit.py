"""
Helper script for hitting the rate limits of Docker Hub and other registries (on purpose).
"""
import asyncio
import logging
import string
import time
import sys
import random

from docker_registry_client_async import DockerRegistryClientAsync, ImageName

logger = logging.getLogger("DatabaseUpdater")


async def probe_rate_limit(registry_client, start_rate=1, max_rate=200, step=10, duration=5):
    """
    Probes API rate limit by sending requests at controlled rates (parallelized).

    Args:
        start_rate: starting requests/sec
        max_rate: maximum requests/sec to test
        step: increment in requests/sec between tests
        duration: how many seconds to sustain each rate

    Returns:
        Maximum safe requests/sec observed
    """
    safe_rate = 0



    async def make_request() -> bool:
        try:
            random_a_to_z_string = ''.join(random.choices(string.ascii_lowercase, k=10))
            # image_name = ImageName.parse(f"mirror.gcr.io/library/busybox:{random_a_to_z_string}")
            image_name = ImageName.parse(f"index.docker.io/library/busybox:{random_a_to_z_string}")
            registry_client.tokens.clear()
            response = await registry_client.head_manifest(image_name)
            if response.client_response.status not in (200, 429, 404):
                logger.debug(f"Received unexpected status code: {response.client_response.status}")
            if response.client_response.status == 404:
                logger.info(f"OK")
            elif response.client_response.status == 429:
                logger.info(f"Rate limited (429)")
            return response.client_response.status == 404
        except Exception as e:
            return False

    for rate in range(start_rate, max_rate + 1, step):
        logger.info(f"Starting requests/sec: {rate} for duration: {duration}s")

        successes, failures = 0, 0
        start = time.monotonic()
        elapsed = 0
        while elapsed < duration:
            batch_start = time.monotonic()
            # Launch 'rate' requests in parallel for this interval
            tasks = [make_request() for _ in range(rate)]
            results = await asyncio.gather(*tasks)
            successes += sum(1 for r in results if r)
            failures += sum(1 for r in results if not r)
            batch_duration = time.monotonic() - batch_start
            sleep_time = 1.0 - batch_duration
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            else:
                logger.debug(f"Warning: batch took longer than 1s, cannot maintain rate: sleep_time={sleep_time:.3f}, batch_duration={batch_duration:.3f}")
            elapsed = time.monotonic() - start

        logger.info(f"Results at {rate} req/s: {successes} ok, {failures} rate-limited")

        if failures > 0:
            logger.info(f"❌ Rate {rate} req/s exceeds limit.")
            break
        else:
            safe_rate = rate

    logger.info(f"\n✅ Safe rate limit: ~{safe_rate} requests/sec")
    return safe_rate


async def main():
    async with DockerRegistryClientAsync() as registry_client:
        await probe_rate_limit(registry_client, start_rate=60, max_rate=61, step=10, duration=600)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("SIGINT detected, exiting...")
