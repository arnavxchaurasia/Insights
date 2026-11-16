import json
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(1000), unique=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    etag: Mapped[str | None] = mapped_column(String(500))
    last_modified: Mapped[str | None] = mapped_column(String(100))
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_status: Mapped[str | None] = mapped_column(String(300))


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    url: Mapped[str] = mapped_column(String(2000))
    url_hash: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(1000))
    summary: Mapped[str] = mapped_column(Text, default="")
    # All datetimes are stored as naive UTC.
    published_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
    cluster_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)

    source: Mapped[Source] = relationship()
    tag: Mapped[ArticleTag | None] = relationship(
        back_populates="article", uselist=False, cascade="all, delete-orphan"
    )
    impact: Mapped[ArticleImpact | None] = relationship(
        back_populates="article", uselist=False, cascade="all, delete-orphan"
    )


class ArticleTag(Base):
    __tablename__ = "article_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), unique=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), index=True, default="other")
    sectors_json: Mapped[str] = mapped_column(Text, default="[]")
    companies_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime)

    article: Mapped[Article] = relationship(back_populates="tag")

    @property
    def sectors(self) -> list[str]:
        try:
            return json.loads(self.sectors_json)
        except Exception:
            return []

    @property
    def companies(self) -> list[str]:
        try:
            return json.loads(self.companies_json)
        except Exception:
            return []


class ArticleImpact(Base):
    __tablename__ = "impacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), unique=True, index=True
    )
    first_order_json: Mapped[str] = mapped_column(Text, default="[]")
    second_order_json: Mapped[str] = mapped_column(Text, default="[]")
    horizon: Mapped[str] = mapped_column(String(50), default="1-4q")
    confidence: Mapped[float] = mapped_column(Float)
    evidence: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    article: Mapped[Article] = relationship(back_populates="impact")

    @property
    def first_order(self) -> list[dict[str, Any]]:
        try:
            val = json.loads(self.first_order_json)
            return val if isinstance(val, list) else []
        except Exception:
            return []

    @property
    def second_order(self) -> list[dict[str, Any]]:
        try:
            val = json.loads(self.second_order_json)
            return val if isinstance(val, list) else []
        except Exception:
            return []
