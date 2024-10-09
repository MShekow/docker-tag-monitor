import reflex as rx

from ..state import ImageDetailsState


def digests_graph() -> rx.Component:
    return rx.vstack(
        rx.select(
            ["weekly", "monthly"],
            value=ImageDetailsState.aggregation_interval,
            on_change=ImageDetailsState.change_aggregation_interval,
        ),
        rx.card(
            rx.recharts.bar_chart(
                rx.recharts.bar(
                    data_key="count",
                    stroke=rx.color("accent", 8),
                    fill=rx.color("accent", 3),
                ),
                rx.recharts.x_axis(type_="number"),
                rx.recharts.y_axis(
                    data_key="label", type_="category", width=200  # TODO do we really need to set the width?
                ),
                data=ImageDetailsState.digest_updates_graph_data,
                layout="vertical",
                margin={
                    "top": 20,
                    "right": 20,
                    "left": 20,
                    "bottom": 20,
                },
                width="100%",
                height=500,  # TODO: needs a better solution
            ),
            width="100%",
        ),
        width="100%",
    )
