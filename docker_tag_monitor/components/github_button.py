import reflex as rx

from docker_tag_monitor.constants import PROJECT_URL
from docker_tag_monitor.state import NavbarState


def github_button() -> rx.Component:
    return rx.button(
        rx.icon("github"),
        rx.text("GitHub"),
        rx.badge(NavbarState.github_stars, color_scheme="gray"),
        on_click=rx.redirect(
            PROJECT_URL,
            is_external=True,
        ),
        variant="outline",
    )
