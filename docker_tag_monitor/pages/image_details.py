import reflex as rx

from ..components.digests_graph import digests_graph
from ..components.digests_table import digests_table
from ..main_template import template
from ..state import ImageDetailsState


# TODO don't show "Image details" in navbar menu, unless the route is active

@template(route="/details/[...image_name]", title="Image details", on_load=ImageDetailsState.on_page_load)
def index() -> rx.Component:
    return rx.vstack(
        rx.center(
            rx.heading("Image details", size="9"),
            width="100%"
        ),
        rx.cond(ImageDetailsState.loading,
                rx.hstack(
                    rx.spinner(size="3"),
                    rx.text("Loading..."),
                    align="center",
                    gap="1em",
                )
                ),
        rx.cond(ImageDetailsState.error,
                rx.callout(
                    rx.vstack(
                        rx.text("The provided repository/image/tag is invalid."),
                        rx.text("Please provide a valid format: [some.registry.com[:1234]/][foo/]repo-name[:tag-name]")
                    ),
                    icon="triangle_alert",
                    color_scheme="red",
                    role="alert",
                )),
        rx.cond(ImageDetailsState.not_found,
                rx.callout(
                    rx.vstack(
                        rx.text(
                            "This repository / image / tag has been successfully added to the monitoring database."),
                        rx.text("No monitoring data is available yet. Please revisit this page at a later time."),
                    ),
                    icon="info",
                    color_scheme="green",
                    role="alert",
                )),
        rx.cond(ImageDetailsState.non_existent_image,
                rx.callout("The provided image does not exist in the respective registry!",
                           icon="info",
                           color_scheme="green",
                           role="alert",
                           )),
        rx.cond(~ImageDetailsState.loading & ImageDetailsState.image_to_scrape,
                rx.card(
                    rx.data_list.root(
                        rx.data_list.item(
                            rx.data_list.label("Registry"),
                            rx.data_list.value(ImageDetailsState.image_to_scrape.endpoint),
                            align="center",
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Repository"),
                            rx.data_list.value(ImageDetailsState.image_to_scrape.image),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Tag"),  # TODO: offer ability to switch to tags of the same repo/image
                            rx.data_list.value(ImageDetailsState.image_to_scrape.tag),
                            align="center",
                        ),
                    ),
                ),
                ),
        rx.cond(ImageDetailsState.digest_updates_graph_data, digests_graph()),
        rx.cond(ImageDetailsState.digest_items, digests_table()),
        spacing="8",
        width="100%",
    )
