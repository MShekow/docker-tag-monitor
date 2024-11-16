import reflex as rx

from . import styles

app = rx.App(
    style=styles.base_style,
    stylesheets=styles.base_stylesheets
)

# TODO: figure out how we can set e.g. logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO) such that it works
