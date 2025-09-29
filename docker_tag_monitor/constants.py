import os

import durationpy

NAMESPACE_AND_REPO = "MShekow/docker-tag-monitor"
PROJECT_URL = f"https://github.com/{NAMESPACE_AND_REPO}"
GITHUB_STARS_REFRESH_INTERVAL_SECONDS = 3600

ORDERED_PAGE_ROUTES = [  # Note: keep these in sync with the "@template(route=...)" decorators
    "/",
    "/details/[[...splat]]",
    "/status",
]

MAX_DAILY_SCAN_ENTRIES_IN_GRAPH = 50

IMAGE_LAST_VIEWED_UPDATE_THRESHOLD = durationpy.from_str(os.getenv("IMAGE_LAST_VIEWED_UPDATE_THRESHOLD", "1d"))
"""
It is overkill to update ImageToScape.last_viewed to <now> each and every time a user accesses the image details page.
This interval specifies how much time must have passed since the last ImageToScape.last_viewed update for it to be
updated to <now>.
"""

POPULAR_IMAGES_MAX_COUNT = 50

# URL was reverse engineered (via browser web dev tools) from the page
# https://hub.docker.com/search?type=image&image_filter=official%2Cstore%2Copen_source
DOCKERHUB_IMAGE_QUERY_URL = (f"https://hub.docker.com/api/search/v3/catalog/search?from=0"
                             f"&size={POPULAR_IMAGES_MAX_COUNT}&query="
                             "&type=image&source=store&official=true&open_source=true")
DOCKERHUB_LIST_TAGS_FOR_IMAGE_URL = ("https://hub.docker.com/v2/repositories/{image_name}/tags"
                                     "?page_size={tags_per_image}&ordering=last_updated")
