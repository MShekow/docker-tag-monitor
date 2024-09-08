from datetime import datetime

import reflex as rx
import sqlmodel
from sqlalchemy import UniqueConstraint


class BackgroundJobExecution(rx.Model, table=True):
    __tablename__ = "background_job_execution"
    started: datetime
    completed: datetime
    successful_queries: int
    failed_queries: int


class ImageToScrape(rx.Model, table=True):
    __tablename__ = "image_to_scrape"
    __table_args__ = (
        UniqueConstraint("endpoint", "image", "tag", name="endpoint_image_tag"),
    )
    endpoint: str = sqlmodel.Field(index=True)
    image: str = sqlmodel.Field(index=True)
    tag: str = sqlmodel.Field(index=True)


class ImageUpdate(rx.Model, table=True):
    __tablename__ = "image_update"
    scraped_at: datetime
    image_id: int = sqlmodel.Field(foreign_key="image_to_scrape.id", index=True)
    digest: str
