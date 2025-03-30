from datetime import datetime
from typing import List

import reflex as rx
import sqlalchemy as sa
import sqlmodel


class BackgroundJobExecution(rx.Model, table=True):
    __tablename__ = "background_job_execution"
    started: datetime = sqlmodel.Field(sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, index=True))
    completed: datetime = sqlmodel.Field(sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, index=True))
    successful_queries: int
    failed_queries: int


class ScrapedImage(rx.Model, table=True):
    """
    Helper table that keeps tracks of all tags of an image (updated every digest refresh cycle).
    """
    __tablename__ = "scraped_image"
    __table_args__ = (
        sa.UniqueConstraint("endpoint", "image", name="endpoint_with_image"),
    )
    endpoint: str
    image: str
    known_tags: List[float] = sqlmodel.Field(
        sa_column=sqlmodel.Column(sqlmodel.ARRAY(sqlmodel.String), server_default="{}"))


class ImageToScrape(rx.Model, table=True):
    __tablename__ = "image_to_scrape"
    __table_args__ = (
        sa.UniqueConstraint("endpoint", "image", "tag", name="endpoint_image_tag"),
        sa.Index("compound_index_endpoint_image", "endpoint", "image"),
    )
    endpoint: str = sqlmodel.Field(index=True)
    image: str = sqlmodel.Field(index=True)
    tag: str = sqlmodel.Field(index=True)
    added_at: datetime = sqlmodel.Field(
        sa_column=sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(), index=True))
    last_viewed: datetime = sqlmodel.Field(sa_column=sa.Column(sa.DateTime(timezone=True),
                                                               server_default=sa.func.now(), index=True))


class ImageUpdate(rx.Model, table=True):
    __tablename__ = "image_update"
    scraped_at: datetime = sqlmodel.Field(
        sa_column=sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(), index=True))
    image_id: int = sqlmodel.Field(foreign_key="image_to_scrape.id", index=True, ondelete="CASCADE")
    digest: str
