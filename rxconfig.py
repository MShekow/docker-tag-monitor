import reflex as rx

# Note, you can override the values via env vars that are simply capitalized

config = rx.Config(
    app_name="docker_tag_monitor",
    show_built_with_reflex=False,
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ],
)
