from datetime import datetime

import reflex as rx
import sqlalchemy as sa
import sqlmodel


class BackgroundJobExecution(rx.Model, table=True):
    __tablename__ = "background_job_execution"
    started: datetime = sqlmodel.Field(sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, index=True))
    completed: datetime = sqlmodel.Field(sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, index=True))
    successful_queries: int
    failed_queries: int


class ImageToScrape(rx.Model, table=True):
    __tablename__ = "image_to_scrape"
    __table_args__ = (
        sa.UniqueConstraint("endpoint", "image", "tag", name="endpoint_image_tag"),
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
