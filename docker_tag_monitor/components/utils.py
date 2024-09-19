from docker_tag_monitor.models import ImageToScrape
import reflex as rx


def clickable_image_details_link(text: str, image_to_scrape: ImageToScrape) -> rx.Component:
    return rx.link(text,
                   href=f"/details/{image_to_scrape.endpoint}/{image_to_scrape.image}:{image_to_scrape.tag}")
