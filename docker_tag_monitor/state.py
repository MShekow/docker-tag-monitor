import re
import time
from typing import Optional

import reflex as rx
import requests
from docker_registry_client_async import ImageName, DockerRegistryClientAsync
from sqlmodel import select, func, col

from .constants import NAMESPACE_AND_REPO, GITHUB_STARS_REFRESH_INTERVAL_SECONDS
from .models import ImageToScrape, ImageUpdate


class OverviewTableState(rx.State):
    items: list[ImageToScrape] = []

    total_items: int = 0
    offset: int = 0
    items_per_page: int = 12

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


async def image_exists_in_registry(image_name: ImageName) -> bool:
    async with DockerRegistryClientAsync() as registry_client:
        try:
            result = await registry_client.head_manifest(image_name)
            return result.result
        except Exception as e:
            return False

class ImageDetailsState(rx.State):
    error: bool = False
    loading: bool = True
    not_found: bool = False
    non_existent_image: bool = False
    image_to_scrape: Optional[ImageToScrape] = None

    items: list[ImageUpdate] = []

    total_items: int = 0
    offset: int = 0
    items_per_page: int = 12

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
            self.load_digest_table_data_for_page()

    def next_page(self):
        if self.page_number < self.total_pages:
            self.offset += self.items_per_page
            self.load_digest_table_data_for_page()

    def first_page(self):
        self.offset = 0
        self.load_digest_table_data_for_page()

    def last_page(self):
        self.offset = (self.total_pages - 1) * self.items_per_page
        self.load_digest_table_data_for_page()

    def load_digest_table_data_for_page(self):
        with rx.session() as session:
            select_query = ImageUpdate.select().where(ImageUpdate.image_id == self.image_to_scrape.id).offset(
                self.offset).limit(self.items_per_page)
            self.items = session.exec(select_query).all()

    async def on_page_load(self):
        # Reset vars to default
        self.error = False
        self.loading = True
        self.not_found = False
        self.non_existent_image = False
        self.image_to_scrape = None
        self.items.clear()

        yield  # send the update to the UI immediately(!)

        try:
            image_segments_from_url: Optional[list[str]] = self.router.page.params.get("image_name", None)

            if not image_segments_from_url:
                self.error = True
                return

            image_name_str = "/".join(image_segments_from_url)

            try:
                image_name = ImageName.parse(image_name_str)
                validate_image_name(image_name)
            except ValueError:
                self.error = True
                return

            resolved_registry = image_name.resolve_endpoint()
            resolved_image = image_name.resolve_image()
            resolved_tag = image_name.resolve_tag()

            with rx.session() as session:
                query = ImageToScrape.select().where(ImageToScrape.endpoint == resolved_registry,
                                                     ImageToScrape.image == resolved_image,
                                                     ImageToScrape.tag == resolved_tag)
                image_to_scrape: Optional[ImageToScrape] = session.exec(query).first()
                if image_to_scrape is None:
                    if not await image_exists_in_registry(image_name):
                        self.non_existent_image = True
                        return

                    image_to_scrape = ImageToScrape(
                        endpoint=resolved_registry,
                        image=resolved_image,
                        tag=resolved_tag,
                    )
                    session.add(image_to_scrape)
                    session.commit()
                    session.refresh(image_to_scrape)  # ensures that the ".id" field of image_to_scrape is populated

                    self.image_to_scrape = image_to_scrape

                    self.not_found = True
                    return

                self.image_to_scrape = image_to_scrape

                # print(f"ID: {self.image_to_scrape.id}")
                count_query = select(func.count(ImageUpdate.id)).where(ImageUpdate.image_id == self.image_to_scrape.id)
                # print(count_query)
                self.total_items = session.exec(count_query).one()

                # print(f"Total items: {self.total_items}")

                if self.total_items == 0:
                    self.not_found = True
                    return

            self.load_digest_table_data_for_page()
        finally:
            self.loading = False


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
            # print("search_term is empty")
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

github_stars = ""
github_starts_last_refresh = -9999.9

class NavbarState(rx.State):

    @rx.var
    def github_stars(self) -> str:
        """
        Refreshes the GitHub stars count every GITHUB_STARS_REFRESH_INTERVAL_SECONDS seconds (to avoid GitHub API
        throttling).
        """
        global github_stars
        global github_starts_last_refresh

        if github_starts_last_refresh + GITHUB_STARS_REFRESH_INTERVAL_SECONDS > time.monotonic():
            return github_stars

        github_starts_last_refresh = time.monotonic()

        try:
            response = requests.get(f"https://api.github.com/repos/{NAMESPACE_AND_REPO}")
            data = response.json()
            github_stars_from_resp: int = data["stargazers_count"]

            if github_stars_from_resp >= 1000:
                github_stars = f"{github_stars_from_resp / 1000:.1f}K"  # turns e.g. 1234 into 1.2K
            github_stars = str(github_stars_from_resp)
        except Exception:
            pass

        return github_stars
