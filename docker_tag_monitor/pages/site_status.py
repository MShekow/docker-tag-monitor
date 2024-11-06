import reflex as rx

from ..components.daily_scan_summary_graph import daily_scan_summary_graph
from ..main_template import template
from ..state import StatusState


@template(route="/status", title="Site status", on_load=StatusState.load_data)
def index() -> rx.Component:
    return rx.vstack(
        rx.center(
            rx.heading("Site status", size="9"),
            width="100%"
        ),
        rx.text("Docker Tag Monitor scans for tag updates in a separate background process that runs hourly. This "
                "graph shows a daily summary of the successful and failed scans."),
        daily_scan_summary_graph(),
        rx.text("The next graph shows the average scan duration per day."),
        # TODO: add graph
        spacing="8",
        width="100%",
    )
