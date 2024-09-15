from dataclasses import dataclass

import reflex as rx
from sqlmodel import select, func

from .models import ImageToScrape


class OverviewTableState(rx.State):
    items: list[ImageToScrape] = []

    total_items: int = 0
    offset: int = 0
    items_per_page: int = 12  # Number of rows per page

    @rx.var(cache=True)
    def page_number(self) -> int:
        return (
                (self.offset // self.items_per_page)
                + 1
                + (1 if self.offset % self.items_per_page else 0)
        )

    @rx.var(cache=True)
    def total_pages(self) -> int:
        return (self.total_items // self.items_per_page) + (
            1 if self.total_items % self.items_per_page else 0
        )

    def prev_page(self):
        if self.page_number > 1:
            self.offset -= self.items_per_page
            self.load_data()

    def next_page(self):
        if self.page_number < self.total_pages:
            self.offset += self.items_per_page
            self.load_data()

    def first_page(self):
        self.offset = 0
        self.load_data()

    def last_page(self):
        self.offset = (self.total_pages - 1) * self.items_per_page
        self.load_data()

    def load_data(self):
        with rx.session() as session:
            select_query = ImageToScrape.select().offset(self.offset).limit(self.items_per_page)
            self.items = session.exec(select_query).all()

            self.total_items = session.exec(select(func.count(ImageToScrape.id))).one()

"""
Search:

SearchState class, it has the search string as variable
    Method "validate_and_search(input)":
        - If input is empty, show the search help text
        - Parse with ImageName.parse(), if ValueError, set "error" to True
        - Make database query, using LIKE (?) for each part of the input, set upper limit of e.g. 5, return them
        - Set unknown_image to True if no results are found

Use rx.debounce_input wrapping a rx.input
"""
