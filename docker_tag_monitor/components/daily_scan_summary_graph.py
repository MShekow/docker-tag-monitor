import reflex as rx

from ..state import StatusState


def daily_scan_summary_graph() -> rx.Component:
    return rx.card(
        rx.recharts.bar_chart(
            rx.recharts.bar(
                data_key="successful_scans",
                stroke=rx.color("green", 8),
                fill=rx.color("green", 9),
                name="Successful scans",
                stack_id="1"
            ),
            rx.recharts.bar(
                data_key="failed_scans",
                stroke=rx.color("red", 8),
                fill=rx.color("red", 9),
                name="Failed scans",
                stack_id="1"
            ),
            rx.recharts.x_axis(data_key="date", angle=70, text_anchor="start"),
            rx.recharts.y_axis(),
            rx.recharts.legend(vertical_align="top"),
            data=StatusState.daily_scan_summary_graph_data,
            margin={
                "top": 40,
                "right": 40,
                "left": 0,
                "bottom": 80,
            },
            width="100%",
            height=500,
        ),
        width="100%"
    )
