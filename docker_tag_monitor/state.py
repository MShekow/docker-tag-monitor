import re

import reflex as rx
from docker_registry_client_async import ImageName
from sqlmodel import select, func, col

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


TAG_PATTERN = re.compile(r'[a-zA-Z0-9_][a-zA-Z0-9._-]{0,127}')
IMAGE_PATTERN = re.compile(r'[a-z0-9]+((\.|_|__|-+)[a-z0-9]+)*(\/[a-z0-9]+((\.|_|__|-+)[a-z0-9]+)*)*')


def validate_image_name(image_name: ImageName):
    """
    Raises ValueError in case the endpoint/host format or the image/tag format is invalid (which the
    docker-registry-client-async library does not seem to verify). See also
    https://github.com/opencontainers/distribution-spec/blob/main/spec.md#pull
    """
    if image_name.endpoint:
        hostname, sep, port = image_name.endpoint.partition(":")
        if port and (not port.isdigit() or not (0 <= int(port) <= 65535)):
            raise ValueError(f"Invalid port number: {port}")

    if image_name.tag:
        if not bool(TAG_PATTERN.fullmatch(image_name.tag)):
            raise ValueError(f"Invalid tag format: {image_name.tag}")

    if image_name.image:
        if not bool(IMAGE_PATTERN.fullmatch(image_name.image)):
            raise ValueError(f"Invalid image format: {image_name.image}")


class SearchState(rx.State):
    search_string: str = ""
    error: bool = False
    unknown_image: bool = False
    search_results: list[ImageToScrape] = []

    def clear_search(self):
        self.validate_and_search("")

    def validate_and_search(self, search_term: str):
        self.search_string = search_term
        self.error = False
        self.unknown_image = False

        if not search_term:
            self.search_results.clear()
            print("search_term is empty")
            return

        try:
            image_name = ImageName.parse(search_term)
            validate_image_name(image_name)
        except ValueError:
            self.error = True
            return

        with rx.session() as session:
            query = select(ImageToScrape).where(
                col(ImageToScrape.endpoint).contains(image_name.resolve_endpoint()),
                col(ImageToScrape.image).contains(image_name.resolve_image()),
            )

            if image_name.tag:
                query = query.where(col(ImageToScrape.tag).contains(image_name.tag))

            query = query.limit(5)

            self.search_results = session.exec(query).all()

            if not self.search_results:
                self.unknown_image = True
