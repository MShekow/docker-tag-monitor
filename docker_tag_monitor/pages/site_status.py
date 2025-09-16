import reflex as rx

from ..components.daily_scan_duration_graph import daily_scan_duration_graph
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
                "graph shows a daily summary of the successful and failed scan runs. A failed run means that of the "
                "thousands of tags scanned during that run, there was at least one tag whose digest could not be "
                "retrieved from the respective image registry (e.g., due to rate limiting or connection issues)."),
        daily_scan_summary_graph(),
        rx.text("The next graph shows the average scan run duration per day."),
        daily_scan_duration_graph(),
        spacing="8",
        width="100%",
    )
