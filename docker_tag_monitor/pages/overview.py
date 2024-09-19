import reflex as rx

from ..components.overview_table import overview_table
from ..components.search import search_bar
from ..main_template import template


@template(route="/", title="Overview")
def index() -> rx.Component:
    return rx.vstack(
        rx.center(
            rx.heading("Docker Tag Monitor", size="9"),
            width="100%"
        ),
        rx.text(
            "Docker Tag Monitor provides insights into the update frequency of Docker/OCI image tags. "
            "It scrapes a few popular images by default, but allows you to add more tags."),
        search_bar(),
        overview_table(),  # TODO: show another column with the tag updates, sorted by the most active ones
        spacing="8",
        width="100%",
    )
