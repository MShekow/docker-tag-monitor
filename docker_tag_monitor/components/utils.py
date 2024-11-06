from datetime import datetime, timedelta
from typing import TypedDict

import reflex as rx


class ImageToScrapeWithCount(TypedDict):
    endpoint: str
    image: str
    tag: str
    added_at: str
    image_update_count: int


class ImageUpdateAggregated(TypedDict):
    interval_start: datetime
    count: int


class ImageUpdateGraphData(TypedDict):
    label: str
    count: int


class DailyScanSummary(TypedDict):
    date: str
    successful_scans: int
    failed_scans: int


class DailyScanDuration(TypedDict):
    date: str
    duration_minutes: float


def clickable_image_details_link(text: str, image_to_scrape: ImageToScrapeWithCount) -> rx.Component:
    return rx.link(text,
                   href=f"/details/{image_to_scrape["endpoint"]}/{image_to_scrape["image"]}:{image_to_scrape["tag"]}")


def format_graph_labels(digest_updates_aggregated: list[ImageUpdateAggregated],
                        aggregation_interval: str) -> list[ImageUpdateGraphData]:
    def label(start: datetime) -> str:
        if aggregation_interval == "weekly":
            end = start + timedelta(days=6)
            return f"{start.strftime("%b %d")} - {end.strftime("%b %d %Y")}"
        if aggregation_interval == "monthly":
            return start.strftime("%b %Y")

    return [{"label": label(x["interval_start"]), "count": x["count"]} for x in digest_updates_aggregated]
