import os

import durationpy

NAMESPACE_AND_REPO = "MShekow/docker-tag-monitor"
PROJECT_URL = f"https://github.com/{NAMESPACE_AND_REPO}"
GITHUB_STARS_REFRESH_INTERVAL_SECONDS = 3600

ORDERED_PAGE_ROUTES = [  # Note: keep these in sync with the "@template(route=...)" decorators
    "/",
    "/details/[...image_name]",
    "/status",
]

MAX_DAILY_SCAN_ENTRIES_IN_GRAPH = 50

IMAGE_LAST_VIEWED_UPDATE_THRESHOLD = durationpy.from_str(os.getenv("IMAGE_LAST_VIEWED_UPDATE_THRESHOLD", "1d"))
"""
It is overkill to update ImageToScape.last_viewed to <now> each and every time a user accesses the image details page.
This interval specifies how much time must have passed since the last ImageToScape.last_viewed update for it to be
updated to <now>.
"""
