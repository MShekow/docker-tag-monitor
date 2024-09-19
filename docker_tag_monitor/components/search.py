import reflex as rx

from .utils import clickable_image_details_link
from ..state import SearchState


def search_bar() -> rx.Component:
    return rx.fragment(
        rx.debounce_input(
            rx.input(
                rx.input.slot(rx.icon("search")),
                rx.input.slot(
                    rx.icon("x"),
                    justify="end",
                    cursor="pointer",
                    on_click=SearchState.clear_search,
                    display=rx.cond(SearchState.search_string, "flex", "none"),
                ),
                value=SearchState.search_string,
                placeholder="Search for [registry/]image[:tag]",
                size="3",
                width=["100%", "100%", "100%", "60%"],
                variant="surface",
                color_scheme="gray",
                on_change=SearchState.validate_and_search,
            ), debounce_timeout=500),
        rx.card(  # Shows the search results
            rx.cond(
                SearchState.search_string,
                rx.text("Search results for: " + SearchState.search_string, margin_bottom="10px"),
                # If no search term is entered, show this placeholder:
                rx.text("Please enter a search term to see the results here ..."),
            ),
            rx.cond(
                SearchState.error,
                rx.callout(
                    "Invalid image/tag format",
                    icon="triangle_alert",
                    color_scheme="red",
                    role="alert",
                )),
            rx.cond(SearchState.unknown_image, rx.callout(
                rx.text("No images found. Click ", rx.link("here", href=f"/details/{SearchState.search_string}"),
                        " to monitor this image/tag"),
                icon="info",
                color_scheme="green",
                role="alert",
            )),
            rx.cond(SearchState.search_results,
                    rx.vstack(
                        rx.foreach(SearchState.search_results,
                                   lambda item: clickable_image_details_link(f"{item.endpoint}/{item.image}:{item.tag}",
                                                                             item))),
                    ),
            size="1"),
    )
