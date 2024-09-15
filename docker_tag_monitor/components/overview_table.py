import reflex as rx

from ..models import ImageToScrape
from ..state import OverviewTableState


def _header_cell(text: str, icon: str) -> rx.Component:
    return rx.table.column_header_cell(
        rx.hstack(
            rx.icon(icon, size=18),
            rx.text(text),
            align="center",
            spacing="2",
        ),
    )


def _pagination_view() -> rx.Component:
    return rx.hstack(
        rx.text(
            "Page ",
            rx.code(OverviewTableState.page_number),
            f" of {OverviewTableState.total_pages}",
            justify="end",
        ),
        rx.hstack(
            rx.icon_button(
                rx.icon("chevrons-left", size=18),
                on_click=OverviewTableState.first_page,
                opacity=rx.cond(OverviewTableState.page_number == 1, 0.6, 1),
                color_scheme=rx.cond(OverviewTableState.page_number == 1, "gray", "accent"),
                variant="soft",
            ),
            rx.icon_button(
                rx.icon("chevron-left", size=18),
                on_click=OverviewTableState.prev_page,
                opacity=rx.cond(OverviewTableState.page_number == 1, 0.6, 1),
                color_scheme=rx.cond(OverviewTableState.page_number == 1, "gray", "accent"),
                variant="soft",
            ),
            rx.icon_button(
                rx.icon("chevron-right", size=18),
                on_click=OverviewTableState.next_page,
                opacity=rx.cond(
                    OverviewTableState.page_number == OverviewTableState.total_pages, 0.6, 1
                ),
                color_scheme=rx.cond(
                    OverviewTableState.page_number == OverviewTableState.total_pages,
                    "gray",
                    "accent",
                ),
                variant="soft",
            ),
            rx.icon_button(
                rx.icon("chevrons-right", size=18),
                on_click=OverviewTableState.last_page,
                opacity=rx.cond(
                    OverviewTableState.page_number == OverviewTableState.total_pages, 0.6, 1
                ),
                color_scheme=rx.cond(
                    OverviewTableState.page_number == OverviewTableState.total_pages,
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


def show_image(item: ImageToScrape, index: int) -> rx.Component:
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
        rx.table.cell(item.endpoint),
        rx.table.cell(item.image),
        rx.table.cell(item.tag),
        style={"_hover": {"bg": hover_color}, "bg": bg_color},
        align="center",
    )


def overview_table() -> rx.Component:
    return rx.box(
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Registry"),
                    rx.table.column_header_cell("Repository"),
                    rx.table.column_header_cell("Tag"),
                ),
            ),
            rx.table.body(
                rx.foreach(
                    OverviewTableState.items,
                    lambda item, index: show_image(item, index),
                )
            ),
            variant="surface",
            size="3",
            width="100%",
            on_mount=OverviewTableState.load_data,
        ),
        _pagination_view(),
        width="100%",
    )
