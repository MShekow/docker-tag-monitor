"""Sidebar component for the app."""
from .github_button import github_button
from .. import styles

import reflex as rx

from ..constants import ORDERED_PAGE_ROUTES


def sidebar_header() -> rx.Component:
    """Sidebar header.

    Returns:
        The sidebar header component.
    """
    return rx.hstack(
        # The logo.
        rx.color_mode_cond(
            rx.image(src="/reflex_black.svg", height="1.5em"),
            rx.image(src="/reflex_white.svg", height="1.5em"),
        ),
        rx.spacer(),
        align="center",
        width="100%",
        padding="0.35em",
        margin_bottom="1em",
    )


def sidebar_footer() -> rx.Component:
    """Sidebar footer.

    Returns:
        The sidebar footer component.
    """
    return rx.hstack(
        github_button(),
        rx.spacer(),
        rx.color_mode.button(style={"opacity": "0.8", "scale": "0.95"}),
        justify="start",
        align="center",
        width="100%",
        padding="0.35em",
    )


def sidebar_item_icon(icon: str) -> rx.Component:
    return rx.icon(icon, size=18)


def sidebar_item(text: str, url: str) -> rx.Component:
    """Sidebar item.

    Args:
        text: The text of the item.
        url: The URL of the item.

    Returns:
        rx.Component: The sidebar item component.
    """
    # Whether the item is active.
    active = (rx.State.router.page.path == url.lower()) | (
            (rx.State.router.page.path == "/") & text == "Overview"
    )

    show_item = (rx.State.router.page.path == "/details/[...image_name]")

    return rx.link(
        rx.hstack(
            rx.match(
                text,
                ("Overview", sidebar_item_icon("home")),
                ("Image details", sidebar_item_icon("table-2")),
                ("Site status", sidebar_item_icon("book-open")),
                sidebar_item_icon("layout-dashboard"),  # default, never used
            ),
            rx.text(text, size="3", weight="regular"),
            color=rx.cond(
                active,
                styles.accent_text_color,
                styles.text_color,
            ),
            style={
                "_hover": {
                    "background_color": rx.cond(
                        active,
                        styles.accent_bg_color,
                        styles.gray_bg_color,
                    ),
                    "color": rx.cond(
                        active,
                        styles.accent_text_color,
                        styles.text_color,
                    ),
                    "opacity": "1",
                },
                "opacity": rx.cond(
                    active,
                    "1",
                    "0.95",
                ),
            },
            align="center",
            border_radius=styles.border_radius,
            width="100%",
            spacing="2",
            padding="0.35em",
        ),
        underline="none",
        href=url,
        # display=rx.cond(  # TODO: does not work
        #     show_item,
        #     "flex", "none",
        # ),
        width="100%",
    )


def sidebar() -> rx.Component:
    """The sidebar.

    Returns:
        The sidebar component.
    """
    from reflex.page import get_decorated_pages

    pages = get_decorated_pages()

    # Include all pages even if they are not in the ordered_page_routes.
    ordered_pages = sorted(
        pages,
        key=lambda page: (ORDERED_PAGE_ROUTES.index(page["route"])),
    )

    return rx.flex(
        rx.vstack(
            sidebar_header(),
            rx.vstack(
                *[
                    sidebar_item(
                        text=page.get("title"),
                        url=page["route"],
                    )
                    for page in ordered_pages
                ],
                spacing="1",
                width="100%",
            ),
            rx.spacer(),
            sidebar_footer(),
            justify="end",
            align="end",
            width=styles.sidebar_content_width,
            height="100dvh",
            padding="1em",
        ),
        display=["none", "none", "none", "none", "none", "flex"],
        max_width=styles.sidebar_width,
        width="auto",
        height="100%",
        position="sticky",
        justify="end",
        top="0px",
        left="0px",
        flex="1",
        bg=rx.color("gray", 2),
    )
