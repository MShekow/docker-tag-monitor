NAMESPACE_AND_REPO = "MShekow/docker-tag-monitor"
PROJECT_URL = f"https://github.com/{NAMESPACE_AND_REPO}"
GITHUB_STARS_REFRESH_INTERVAL_SECONDS = 3600

ORDERED_PAGE_ROUTES = [  # Note: keep these in sync with the "@template(route=...)" decorators
    "/",
    "/details/[...image_name]",
    "/status",
]
