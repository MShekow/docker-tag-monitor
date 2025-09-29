import fnmatch
import re
import time
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import reflex as rx
import requests
from dateutil.relativedelta import relativedelta
from docker_registry_client_async import ImageName
from sqlalchemy import text
from sqlmodel import select, func, col

from .components.utils import ImageUpdateAggregated, ImageUpdateGraphData, format_graph_labels, ImageToScrapeWithCount, \
    DailyScanSummary, DailyScanDuration
from .constants import NAMESPACE_AND_REPO, GITHUB_STARS_REFRESH_INTERVAL_SECONDS, \
    MAX_DAILY_SCAN_ENTRIES_IN_GRAPH, IMAGE_LAST_VIEWED_UPDATE_THRESHOLD
from .models import ImageToScrape, ImageUpdate
from .utils import images_exists_in_registry, add_selected_tags_to_monitoring_db, get_additional_image_tags_to_monitor, \
    TAGS_PER_IMAGE_MAX_COUNT


class OverviewTableState(rx.State):
    items: rx.Field[list[ImageToScrapeWithCount]] = rx.field(default_factory=list)

    total_items: int = 0
    offset: int = 0
    items_per_page: int = 12

    @rx.var
    def page_number(self) -> int:
        return (
                (self.offset // self.items_per_page)
                + 1
                + (1 if self.offset % self.items_per_page else 0)
        )

    @rx.var
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
        # Note: we format the date already in SQL instead of doing it in Python, because otherwise Reflex would throw
        # this error when trying to call strftime on the item["added_at"] datetime object:
        # TypeError: You must provide an annotation for the state var `item["added_at"]`.
        # Annotation cannot be `typing.Any`
        query = text("""SELECT
            image_to_scrape.endpoint,
            image_to_scrape.image,
            image_to_scrape.tag,
            TO_CHAR(image_to_scrape.added_at, 'YYYY-MM-DD') AS added_at,
            COUNT(image_update.id) AS image_update_count
        FROM
            image_to_scrape
        LEFT JOIN
            image_update ON image_to_scrape.id = image_update.image_id
        GROUP BY
            image_to_scrape.endpoint, image_to_scrape.image, image_to_scrape.tag, image_to_scrape.added_at
        ORDER BY
            image_update_count DESC
        LIMIT :limit OFFSET :offset;""")

        args = {
            "limit": self.items_per_page,
            "offset": self.offset
        }

        with rx.session() as session:
            self.items.clear()
            for row in session.exec(query, params=args):
                self.items.append(ImageToScrapeWithCount(
                    endpoint=row[0],
                    image=row[1],
                    tag=row[2],
                    added_at=row[3],
                    image_update_count=row[4]
                ))

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


POSTGRESQL_AGGREGATION_INTERVALS = {  # maps the "aggregation_interval" from the UI to the PostgreSQL interval
    "weekly": "week",
    "monthly": "month",
}

IMAGE_DETAILS_PATH_PREFIX = "/details/"


class ImageDetailsState(rx.State):
    error: bool = False
    loading: bool = True
    not_found: bool = False
    non_existent_image: bool = False
    image_to_scrape: Optional[ImageToScrape] = None

    digest_items: rx.Field[list[ImageUpdate]] = rx.field(default_factory=list)
    _digest_updates_aggregated: list[ImageUpdateAggregated] = []  # not sent to the UI
    digest_updates_graph_data: rx.Field[list[ImageUpdateGraphData]] = rx.field(default_factory=list)

    total_items: int = 0
    offset: int = 0
    items_per_page: int = 12
    aggregation_interval: str = "weekly"  # or "monthly", but we cannot use Literal["weekly", "monthly"] in Reflex state

    @rx.var
    def digest_update_graph_height(self) -> int:
        """
        Returns the height of the digest update graph in pixels, which should depend on the number of items in
        self.digest_updates_graph_data.
        Note: the values were experimentally determined. For tables with few rows (e.g. 1), we need a static offset,
        or the rendering would break.
        """
        return 35 * len(self.digest_updates_graph_data) + 60

    @rx.var
    def page_number(self) -> int:
        return (
                (self.offset // self.items_per_page)
                + 1
                + (1 if self.offset % self.items_per_page else 0)
        )

    @rx.var
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
                self.offset).limit(self.items_per_page).order_by(ImageUpdate.scraped_at.desc())
            self.digest_items = session.exec(select_query).all()

    def change_aggregation_interval(self, new_interval: str):
        assert new_interval in ["weekly", "monthly"]
        self.aggregation_interval = new_interval
        self.load_digests_updates_graph_data()

    def load_digests_updates_graph_data(self):
        # should always be the case, but we better check, to avoid SQL injections
        if self.aggregation_interval in POSTGRESQL_AGGREGATION_INTERVALS:
            self._digest_updates_aggregated.clear()
            self.digest_updates_graph_data.clear()

            query = text("""SELECT
                DATE_TRUNC(:aggregation_interval, scraped_at) AS interval_start,
                COUNT(*) AS item_count
            FROM
                image_update
            WHERE
                image_id = :image_id
            GROUP BY
                interval_start
            ORDER BY
                interval_start DESC;""")

            postgresql_aggregation_interval = POSTGRESQL_AGGREGATION_INTERVALS[self.aggregation_interval]
            args = {
                "aggregation_interval": postgresql_aggregation_interval,
                "image_id": self.image_to_scrape.id
            }

            with rx.session() as session:
                for row in session.exec(query, params=args):
                    # Note: row[0] is a datetime object representing the interval start, row[1] is the count as int
                    self._digest_updates_aggregated.append(ImageUpdateAggregated(interval_start=row[0], count=row[1]))

            self.fill_missing_intervals()
            self.digest_updates_graph_data = format_graph_labels(self._digest_updates_aggregated,
                                                                 self.aggregation_interval)

    def fill_missing_intervals(self):
        if len(self._digest_updates_aggregated) < 2:
            return

        start_date = self._digest_updates_aggregated[-1]["interval_start"]
        end_date = self._digest_updates_aggregated[0]["interval_start"]

        # Create a set of existing interval_start dates to simplify the lookup
        existing_dates = {update["interval_start"] for update in self._digest_updates_aggregated}

        # Iterate through each week in the range
        current_date = start_date
        while current_date <= end_date:
            if current_date not in existing_dates:
                self._digest_updates_aggregated.append(ImageUpdateAggregated(interval_start=current_date, count=0))

            if self.aggregation_interval == "weekly":
                current_date += relativedelta(weeks=1)
            elif self.aggregation_interval == "monthly":
                current_date += relativedelta(months=1)
            else:
                raise ValueError(f"Unknown aggregation interval: {self.aggregation_interval}")

        # Sort the list again by interval_start
        self._digest_updates_aggregated.sort(key=lambda update: update["interval_start"], reverse=True)

    async def on_page_load(self):
        # Reset vars to default
        self.error = False
        self.loading = True
        self.not_found = False
        self.non_existent_image = False
        self.image_to_scrape = None
        self.digest_items.clear()
        self._digest_updates_aggregated.clear()
        self.digest_updates_graph_data.clear()

        add_additional_tag_state: AddAdditionalTagsState = await self.get_state(AddAdditionalTagsState)
        add_additional_tag_state.reset()

        yield  # send the update to the UI immediately(!)

        try:
            path: Optional[str] = self.router.url.path  # e.g. "/details/index.docker.io/library/busybox:latest"

            if not path or not path.startswith(IMAGE_DETAILS_PATH_PREFIX):
                self.error = True
                return

            image_name_str = path[len(IMAGE_DETAILS_PATH_PREFIX):]  # e.g. "index.docker.io/library/busybox:latest"

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
                    if not await images_exists_in_registry([image_name]):
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

                count_query = select(func.count(ImageUpdate.id)).where(ImageUpdate.image_id == self.image_to_scrape.id)
                self.total_items = session.exec(count_query).one()

                if self.total_items == 0:
                    self.not_found = True
                    return

                now = datetime.now(ZoneInfo('UTC'))
                last_viewed_age = now - self.image_to_scrape.last_viewed
                if last_viewed_age > IMAGE_LAST_VIEWED_UPDATE_THRESHOLD:
                    self.image_to_scrape.last_viewed = now
                    session.add(self.image_to_scrape)
                    session.commit()

                self.load_digests_updates_graph_data()

            self.load_digest_table_data_for_page()
        finally:
            self.loading = False


class ImageTagField(rx.Base):
    tag: str
    can_add_to_monitoring_db: bool
    checked: bool


class AddAdditionalTagsState(rx.State):
    view_state: str = "show_button"  # alternatives: "show_form", "show_result"
    loading: bool = False
    _image_tags: list[tuple[str, bool]] = []
    shown_image_tag_fields: rx.Field[list[ImageTagField]] = rx.field(default_factory=list)
    select_unselect_all_checked: bool = True
    extra_search_result_count: int = 0
    search_string: str = ""
    error: str = ""

    @rx.event
    async def load_additional_tags(self):
        self.loading = True
        yield  # immediately update the UI

        if not self._image_tags:
            image_details_state: ImageDetailsState = await self.get_state(ImageDetailsState)
            image_name = ImageName.parse(f"{image_details_state.image_to_scrape.endpoint}/"
                                         f"{image_details_state.image_to_scrape.image}:"
                                         f"{image_details_state.image_to_scrape.tag}")
            try:
                self._image_tags = await get_additional_image_tags_to_monitor(image_name)
                self.view_state = "show_form"
            except Exception as e:
                self.error = str(e)
                self._image_tags.clear()

        if self.search_string:
            if '*' in self.search_string or '?' in self.search_string:

                matching_image_tag_fields = [ImageTagField(tag=itf[0], can_add_to_monitoring_db=itf[1], checked=True)
                                             for itf in self._image_tags if
                                             fnmatch.fnmatch(itf[0], self.search_string)]
            else:
                matching_image_tag_fields = [ImageTagField(tag=itf[0], can_add_to_monitoring_db=itf[1], checked=True)
                                             for itf in self._image_tags if self.search_string in itf[0]]

            self.shown_image_tag_fields = matching_image_tag_fields[:TAGS_PER_IMAGE_MAX_COUNT]
            self.extra_search_result_count = max(0, len(matching_image_tag_fields) - TAGS_PER_IMAGE_MAX_COUNT)
        else:
            self.shown_image_tag_fields = [ImageTagField(tag=itf[0], can_add_to_monitoring_db=itf[1], checked=True)
                                           for itf in self._image_tags[:TAGS_PER_IMAGE_MAX_COUNT]]
            self.extra_search_result_count = max(0, len(self._image_tags) - TAGS_PER_IMAGE_MAX_COUNT)

        self.loading = False

    @rx.event
    async def handle_submit(self, _form_data: dict):
        selected_additional_tags = [itf.tag for itf in self.shown_image_tag_fields if
                                    itf.checked and itf.can_add_to_monitoring_db]
        self.loading = True

        yield

        image_details_state: ImageDetailsState = await self.get_state(ImageDetailsState)

        image_name = ImageName.parse(f"{image_details_state.image_to_scrape.endpoint}/"
                                     f"{image_details_state.image_to_scrape.image}:"
                                     f"{image_details_state.image_to_scrape.tag}")

        try:
            await add_selected_tags_to_monitoring_db(image_name, selected_additional_tags)
        except ValueError as e:
            self.error = str(e)

        self.view_state = "show_result"

    @rx.event
    async def clear_search(self):
        self.search_string = ""
        return AddAdditionalTagsState.load_additional_tags

    @rx.event
    async def validate_and_search(self, search_term: str):
        self.search_string = search_term
        return AddAdditionalTagsState.load_additional_tags

    @rx.event
    async def on_check_all(self, checked: bool):
        self.select_unselect_all_checked = checked
        for itf in self.shown_image_tag_fields:
            if itf.can_add_to_monitoring_db:
                itf.checked = checked

    @rx.event
    async def set_checkbox(self, index: int, checked: bool):
        self.shown_image_tag_fields[index].checked = checked
        # If all checkboxes are ticked, also set selected_additional_tags to True
        self.select_unselect_all_checked = all([itf.checked for itf in self.shown_image_tag_fields])


class SearchState(rx.State):
    search_string: str = ""
    error: bool = False
    unknown_image: bool = False
    search_results: rx.Field[list[ImageToScrape]] = rx.field(default_factory=list)

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
            # Note: we use image_name.image (instead of resolve_image()) because the latter would turn "foo"
            # to "library/foo" and thus the search would fail to find (existing) images such as "library/afoo"
            query = select(ImageToScrape).where(
                col(ImageToScrape.endpoint).contains(image_name.resolve_endpoint()),
                col(ImageToScrape.image).contains(image_name.image),
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


class StatusState(rx.State):
    daily_scan_summary_graph_data: rx.Field[list[DailyScanSummary]] = rx.field(default_factory=list)
    daily_scan_duration_graph_data: rx.Field[list[DailyScanDuration]] = rx.field(default_factory=list)

    def load_data(self):
        self.daily_scan_summary_graph_data.clear()
        self.daily_scan_duration_graph_data.clear()

        # Retrieve the aggregation of BackgroundJobExecution objects, returning one row per day, with the columns:
        # -  the day
        # - number of BackgroundJobExecutions where failed_queries is 0 and successful_queries > 0
        # - number of BackgroundJobExecutions where either successful_queries is 0 or failed_queries > 0
        summary_query = text("""WITH date_series AS (
                SELECT generate_series(
                               (SELECT MIN(DATE_TRUNC('day', started)) FROM background_job_execution),
                               (SELECT MAX(DATE_TRUNC('day', started)) FROM background_job_execution),
                               '1 day'::interval
                       )::date AS day
            )
            SELECT
                date_series.day,
                COALESCE(SUM(CASE WHEN background_job_execution.failed_queries = 0 AND background_job_execution.successful_queries > 0 THEN 1 ELSE 0 END), 0) AS successful_scans,
                COALESCE(SUM(CASE WHEN background_job_execution.successful_queries = 0 OR background_job_execution.failed_queries > 0 THEN 1 ELSE 0 END), 0) AS failed_scans
            FROM date_series LEFT JOIN background_job_execution ON
                    DATE_TRUNC('day', background_job_execution.started) = date_series.day
            GROUP BY date_series.day
            ORDER BY date_series.day DESC
            LIMIT :limit""")

        scan_duration_query = text("""WITH date_series AS (
                SELECT 
                    generate_series(
                        (SELECT MIN(DATE(started)) FROM background_job_execution),
                        (SELECT MAX(DATE(completed)) FROM background_job_execution),
                        INTERVAL '1 day'
                    )::date AS execution_date
            )
            SELECT 
                ds.execution_date,
                COALESCE(AVG(EXTRACT(EPOCH FROM (bje.completed - bje.started))), 0) AS average_duration_seconds
            FROM 
                date_series ds
            LEFT JOIN 
                background_job_execution bje ON DATE(bje.started) = ds.execution_date
            GROUP BY ds.execution_date
            ORDER BY ds.execution_date DESC
            LIMIT :limit""")

        with rx.session() as session:
            for row in session.exec(summary_query, params={"limit": MAX_DAILY_SCAN_ENTRIES_IN_GRAPH}):
                # Note: row[0] is a date object representing the day, row[1] and [2] are the successful/failed scans
                daily_scan_summary = DailyScanSummary(date=str(row[0]), successful_scans=row[1], failed_scans=row[2])
                self.daily_scan_summary_graph_data.append(daily_scan_summary)

            for row in session.exec(scan_duration_query, params={"limit": MAX_DAILY_SCAN_ENTRIES_IN_GRAPH}):
                # Note: row[0] is a date object representing the day, row[1] is the
                # duration (seconds) returned as Decimal object, which we need to convert to float
                daily_scan_duration = DailyScanDuration(date=str(row[0]), duration_minutes=float(row[1] / 60))
                self.daily_scan_duration_graph_data.append(daily_scan_duration)

        self.daily_scan_summary_graph_data.reverse()
        self.daily_scan_duration_graph_data.reverse()
