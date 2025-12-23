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


def format_timedelta_human_friendly(td: timedelta) -> str:
    """
    Converts a timedelta to a human-friendly string representation.
    Examples: "6 months", "1 year", "30 days", "2 weeks"
    """
    total_days = td.days

    # Calculate years, months, weeks, days
    years = total_days // 365
    remaining_days = total_days % 365
    months = remaining_days // 30
    remaining_days = remaining_days % 30
    weeks = remaining_days // 7
    days = remaining_days % 7

    parts = []
    if years > 0:
        parts.append(f"{years} year{'s' if years > 1 else ''}")
    if months > 0:
        parts.append(f"{months} month{'s' if months > 1 else ''}")
    if weeks > 0:
        parts.append(f"{weeks} week{'s' if weeks > 1 else ''}")
    if days > 0:
        parts.append(f"{days} day{'s' if days > 1 else ''}")

    # If no parts, it's less than a day
    if not parts:
        hours = td.seconds // 3600
        if hours > 0:
            return f"{hours} hour{'s' if hours > 1 else ''}"
        minutes = (td.seconds % 3600) // 60
        if minutes > 0:
            return f"{minutes} minute{'s' if minutes > 1 else ''}"
        return f"{td.seconds} second{'s' if td.seconds != 1 else ''}"

    # Return the first two most significant parts
    return " and ".join(parts[:2]) if len(parts) <= 2 else ", ".join(parts[:2]) + f", and {parts[2]}"
