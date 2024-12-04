import reflex as rx
from ..state import AddAdditionalTagsState


def _form_component() -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.debounce_input(
                rx.input(
                    rx.input.slot(rx.icon("search")),
                    rx.input.slot(
                        rx.icon("x"),
                        justify="end",
                        cursor="pointer",
                        on_click=AddAdditionalTagsState.clear_search,
                        display=rx.cond(AddAdditionalTagsState.search_string, "flex", "none"),
                    ),
                    value=AddAdditionalTagsState.search_string,
                    placeholder="Search for tag",
                    size="3",
                    width="100%",
                    variant="surface",
                    color_scheme="gray",
                    on_change=AddAdditionalTagsState.validate_and_search,
                ), debounce_timeout=500),
            # rx.checkbox(text="Check / uncheck all", default_checked=True, disabled=AddAdditionalTagsState.loading,
            #             on_change=AddAdditionalTagsState.on_check_all),  does not work :-/
            rx.form.root(
                rx.vstack(
                    rx.text("Please choose which of the following additional tags to add:"),
                    # TODO: needs check/uncheck ALL button. but it's difficult to implement
                    rx.foreach(AddAdditionalTagsState.image_tag_fields,
                               lambda field, idx: rx.hstack(
                                   rx.checkbox(text=field.tag, name=field.tag,
                                               default_checked=AddAdditionalTagsState.image_tag_fields[
                                                   idx].can_add_to_monitoring_db,
                                               disabled=AddAdditionalTagsState.loading | ~
                                               AddAdditionalTagsState.image_tag_fields[idx].can_add_to_monitoring_db,
                                               # on_change=lambda checked: AddAdditionalTagsState.set_checkbox(idx, checked)
                                               ),
                                   rx.cond(~AddAdditionalTagsState.image_tag_fields[idx].can_add_to_monitoring_db,
                                           rx.tooltip(rx.icon("circle-help", size=18),
                                                      content="This tag is already monitored"))
                               )
                               ),
                    rx.button("Add selected version tags",
                              rx.cond(AddAdditionalTagsState.loading, rx.spinner()),
                              type="submit",
                              disabled=AddAdditionalTagsState.loading),

                ),
                on_submit=AddAdditionalTagsState.handle_submit,
                reset_on_submit=False,
            ),
        )
    )


def _result_component() -> rx.Component:
    return rx.callout(
        rx.text("The selected tags were successfully added to the monitoring database."),
        icon="info",
        color_scheme="green",
        role="alert",
    )


def add_image_tags_form() -> rx.Component:
    return rx.vstack(
        rx.cond(
            AddAdditionalTagsState.error,
            rx.callout(
                AddAdditionalTagsState.error,
                icon="triangle_alert",
                color_scheme="red",
                role="alert",
            )),
        rx.match(
            AddAdditionalTagsState.view_state,
            ("show_form", _form_component()),
            ("show_result", _result_component()),
            rx.hstack(
                rx.button(
                    rx.icon("circle-plus"),
                    rx.text("Monitor more tags"),
                    rx.cond(AddAdditionalTagsState.loading, rx.spinner()),
                    disabled=AddAdditionalTagsState.loading,
                    on_click=AddAdditionalTagsState.load_additional_tags
                ),
            )
        )
    )
