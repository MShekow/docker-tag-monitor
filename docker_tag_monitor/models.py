from datetime import datetime
from typing import List

import sqlalchemy as sa
import sqlmodel


class BackgroundJobExecution(sqlmodel.SQLModel, table=True):
    __tablename__ = "background_job_execution"
    id: int | None = sqlmodel.Field(default=None, primary_key=True)
    started: datetime = sqlmodel.Field(sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, index=True))
    completed: datetime = sqlmodel.Field(sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, index=True))
    successful_queries: int
    failed_queries: int


class ScrapedImage(sqlmodel.SQLModel, table=True):
    """
    Helper table that keeps tracks of all tags of an image (updated every digest refresh cycle).
    """
    __tablename__ = "scraped_image"
    __table_args__ = (
        sa.UniqueConstraint("endpoint", "image", name="endpoint_with_image"),
    )
    id: int | None = sqlmodel.Field(default=None, primary_key=True)
    endpoint: str
    image: str
    known_tags: List[float] = sqlmodel.Field(
        sa_column=sqlmodel.Column(sqlmodel.ARRAY(sqlmodel.String), server_default="{}"))


class ImageToScrape(sqlmodel.SQLModel, table=True):
    __tablename__ = "image_to_scrape"
    __table_args__ = (
        sa.UniqueConstraint("endpoint", "image", "tag", name="endpoint_image_tag"),
        sa.Index("compound_index_endpoint_image", "endpoint", "image"),
    )
    id: int | None = sqlmodel.Field(default=None, primary_key=True)
    endpoint: str = sqlmodel.Field(index=True)
    image: str = sqlmodel.Field(index=True)
    tag: str = sqlmodel.Field(index=True)
    added_at: datetime = sqlmodel.Field(
        sa_column=sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(), index=True))
    last_viewed: datetime = sqlmodel.Field(sa_column=sa.Column(sa.DateTime(timezone=True),
                                                               server_default=sa.func.now(), index=True))


class ImageUpdate(sqlmodel.SQLModel, table=True):
    __tablename__ = "image_update"
    id: int | None = sqlmodel.Field(default=None, primary_key=True)
    scraped_at: datetime = sqlmodel.Field(
        sa_column=sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(), index=True))
    image_id: int = sqlmodel.Field(foreign_key="image_to_scrape.id", index=True, ondelete="CASCADE")
    digest: str
