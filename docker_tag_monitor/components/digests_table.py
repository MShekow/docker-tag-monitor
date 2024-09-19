import reflex as rx

from ..models import ImageUpdate
from ..state import ImageDetailsState


def _pagination_view() -> rx.Component:
    return rx.hstack(
        rx.text(
            "Page ",
            rx.code(ImageDetailsState.page_number),
            f" of {ImageDetailsState.total_pages}",
            justify="end",
        ),
        rx.hstack(
            rx.icon_button(
                rx.icon("chevrons-left", size=18),
                on_click=ImageDetailsState.first_page,
                opacity=rx.cond(ImageDetailsState.page_number == 1, 0.6, 1),
                color_scheme=rx.cond(ImageDetailsState.page_number == 1, "gray", "accent"),
                variant="soft",
            ),
            rx.icon_button(
                rx.icon("chevron-left", size=18),
                on_click=ImageDetailsState.prev_page,
                opacity=rx.cond(ImageDetailsState.page_number == 1, 0.6, 1),
                color_scheme=rx.cond(ImageDetailsState.page_number == 1, "gray", "accent"),
                variant="soft",
            ),
            rx.icon_button(
                rx.icon("chevron-right", size=18),
                on_click=ImageDetailsState.next_page,
                opacity=rx.cond(
                    ImageDetailsState.page_number == ImageDetailsState.total_pages, 0.6, 1
                ),
                color_scheme=rx.cond(
                    ImageDetailsState.page_number == ImageDetailsState.total_pages,
                    "gray",
                    "accent",
                ),
                variant="soft",
            ),
            rx.icon_button(
                rx.icon("chevrons-right", size=18),
                on_click=ImageDetailsState.last_page,
                opacity=rx.cond(
                    ImageDetailsState.page_number == ImageDetailsState.total_pages, 0.6, 1
                ),
                color_scheme=rx.cond(
                    ImageDetailsState.page_number == ImageDetailsState.total_pages,
                    "gray",
                    "accent",
                ),
                variant="soft",
            ),
            align="center",
            spacing="2",
            justify="end",
        ),
        spacing="5",
        margin_top="1em",
        align="center",
        width="100%",
        justify="end",
    )


def show_digest(item: ImageUpdate, index: int) -> rx.Component:
    bg_color = rx.cond(
        index % 2 == 0,
        rx.color("gray", 1),
        rx.color("accent", 2),
    )
    hover_color = rx.cond(
        index % 2 == 0,
        rx.color("gray", 3),
        rx.color("accent", 3),
    )
    return rx.table.row(
        rx.table.cell(item.scraped_at),
        rx.table.cell(item.digest),  # TODO: also show the "copy to clipboard" button
        style={"_hover": {"bg": hover_color}, "bg": bg_color},
        align="center",
    )


def digests_table() -> rx.Component:
    return rx.box(
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Tag update"),
                    rx.table.column_header_cell("Tag digest"),
                ),
            ),
            rx.table.body(
                rx.foreach(
                    ImageDetailsState.items,
                    lambda item, index: show_digest(item, index),
                )
            ),
            variant="surface",
            size="3",
            width="100%",
        ),
        _pagination_view(),
        width="100%",
    )
