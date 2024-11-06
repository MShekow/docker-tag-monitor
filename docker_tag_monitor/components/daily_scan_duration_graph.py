import reflex as rx

from ..state import StatusState


def daily_scan_duration_graph() -> rx.Component:
    return rx.card(
        rx.recharts.bar_chart(
            rx.recharts.bar(
                data_key="duration_minutes",
                stroke=rx.color("green", 8),
                fill=rx.color("green", 9),
                name="Duration (minutes)",
            ),
            rx.recharts.x_axis(data_key="date", angle=70, text_anchor="start"),
            rx.recharts.y_axis(),
            rx.recharts.legend(vertical_align="top"),
            data=StatusState.daily_scan_duration_graph_data,
            stack_offset="none",
            margin={
                "top": 40,
                "right": 0,
                "left": 0,
                "bottom": 80,
            },
            width="100%",
            height=400,  # TODO: needs a better solution
        ),
        width="100%"
    )
