import reflex as rx

from docker_tag_monitor import styles
from docker_tag_monitor.components.github_button import github_button
from docker_tag_monitor.constants import ORDERED_PAGE_ROUTES


def menu_item_icon(icon: str) -> rx.Component:
    return rx.icon(icon, size=20)


def menu_item(text: str, url: str) -> rx.Component:
    """Menu item.

    Args:
        text: The text of the item.
        url: The URL of the item.

    Returns:
        rx.Component: The menu item component.
    """
    # Whether the item is active.

    active = (rx.State.router.page.path == url.lower()) | (
            (rx.State.router.page.path == "/") & text == "Overview"
    )

    show_item = (url.lower() != "/details/[...image_name]") | (rx.State.router.page.path == "/details/[...image_name]")

    return rx.link(
        rx.hstack(
            rx.match(
                text,
                ("Overview", menu_item_icon("home")),
                ("Image details", menu_item_icon("table-2")),
                ("Site status", menu_item_icon("book-open")),
                menu_item_icon("layout-dashboard"),
            ),
            rx.text(text, size="4", weight="regular"),
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
            display=rx.cond(
                show_item,
                "flex", "none",
            ),
            border_radius=styles.border_radius,
            width="100%",
            spacing="2",
            padding="0.35em",
        ),
        underline="none",
        href=rx.cond(url.lower() != "/details/[...image_name]", url, "#"),
        width="100%",
    )


def navbar_footer() -> rx.Component:
    """Navbar footer.

    Returns:
        The navbar footer component.
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


def menu_button() -> rx.Component:
    from reflex.page import get_decorated_pages

    pages = get_decorated_pages()

    ordered_pages = sorted(
        pages,
        key=lambda page: ORDERED_PAGE_ROUTES.index(page["route"]),
    )

    return rx.drawer.root(
        rx.drawer.trigger(
            rx.icon("align-justify"),
        ),
        rx.drawer.overlay(z_index="5"),
        rx.drawer.portal(
            rx.drawer.content(
                rx.vstack(
                    rx.hstack(
                        rx.spacer(),
                        rx.drawer.close(rx.icon(tag="x")),
                        justify="end",
                        width="100%",
                    ),
                    rx.divider(),
                    *[
                        menu_item(
                            text=page.get(
                                "title", page["route"].strip("/").capitalize()
                            ),
                            url=page["route"],
                        )
                        for page in ordered_pages
                    ],
                    rx.spacer(),
                    navbar_footer(),
                    spacing="4",
                    width="100%",
                ),
                top="auto",
                left="auto",
                height="100%",
                width="20em",
                padding="1em",
                bg=rx.color("gray", 1),
            ),
            width="100%",
        ),
        direction="right",
    )


def navbar() -> rx.Component:
    """
    The navigation bar that is shown at the top of the page.

    According to https://reflex.dev/docs/styling/responsive/ we hide in case we have the widest possible screen size
    ("xl"), because in this case, we instead show the sidebar.
    """

    return rx.el.nav(
        rx.hstack(
            # The logo.
            rx.color_mode_cond(
                rx.image(src="/reflex_black.svg", height="1em"),  # TODO fix logo
                rx.image(src="/reflex_white.svg", height="1em"),
            ),
            rx.spacer(),
            menu_button(),
            align="center",
            width="100%",
            padding_y="1.25em",
            padding_x=["1em", "1em", "2em"],
        ),
        display=["block", "block", "block", "block" "block", "block", "none"],
        position="sticky",
        background_color=rx.color("gray", 1),
        top="0px",
        z_index="5",
        border_bottom=styles.border,
    )
