"""The overview page of the app."""

import reflex as rx

from ..components.overview_table import overview_table
from ..main_template import template
from ..state import OverviewTableState


@template(route="/", title="Overview")
def index() -> rx.Component:
    return rx.vstack(
        rx.center(
            rx.heading("Docker Tag Monitor", size="9"),
            width="100%"
        ),
        rx.text(
            "Docker Tag Monitor provides insights into the update frequency of Docker/OCI image tags. It scrapes a few popular images by default, but allows you to add more tags."),
        overview_table(),
        rx.popover.root(
            rx.popover.trigger(
                rx.input(
                    rx.input.slot(rx.icon("search")),
                    # rx.input.slot(
                    #     rx.icon("x"),
                    #     justify="end",
                    #     cursor="pointer",
                    #     on_click=TableState.setvar("search_value", ""),
                    #     display=rx.cond(TableState.search_value, "flex", "none"),
                    # ),
                    placeholder="Prompt 1",
                    size="3",
                    max_width=["150px", "150px", "200px", "250px"],
                    min_width=["100px", "100px", "150px", "2--px"],
                    width="100%",
                    variant="surface",
                    color_scheme="gray",
                )
            ),
            rx.popover.content(
                rx.flex(
                    rx.text("Simple Example"),
                    rx.popover.close(
                        rx.button("Close"),
                    ),
                    direction="column",
                    spacing="3",
                ),
            ),
        ),
        spacing="8",
        width="100%",
    )
