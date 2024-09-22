from datetime import datetime, timedelta
from typing import TypedDict, Literal

import reflex as rx

from docker_tag_monitor.models import ImageToScrape


class ImageUpdateAggregated(TypedDict):
    interval_start: datetime
    count: int


class ImageUpdateGraphData(TypedDict):
    label: str
    count: int


def clickable_image_details_link(text: str, image_to_scrape: ImageToScrape) -> rx.Component:
    return rx.link(text,
                   href=f"/details/{image_to_scrape.endpoint}/{image_to_scrape.image}:{image_to_scrape.tag}")


def format_graph_labels(digest_updates_aggregated: list[ImageUpdateAggregated],
                        aggregation_interval: Literal["weekly", "monthly"]) -> list[ImageUpdateGraphData]:
    def label(start: datetime) -> str:
        if aggregation_interval == "weekly":
            end = start + timedelta(days=6)
            return f"{start.strftime("%b %d")} - {end.strftime("%b %d %Y")}"
        if aggregation_interval == "monthly":
            return start.strftime("%b %Y")

    return [{"label": label(x["interval_start"]), "count": x["count"]} for x in digest_updates_aggregated]
