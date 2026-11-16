import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_serializer
from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session, joinedload

from .config import settings
from .db import SessionLocal, get_session, run_migrations
from .ingest import run_ingest, sync_sources
from .models import Article, ArticleTag, Source

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    run_migrations()
    with SessionLocal() as session:
        sync_sources(session)
    scheduler = None
    if settings.run_scheduler:
        scheduler = BackgroundScheduler(timezone="UTC")
        scheduler.add_job(
            run_ingest,
            "interval",
            minutes=settings.ingest_interval_minutes,
            next_run_time=datetime.now(UTC),
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Market Intel API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)
SessionDep = Annotated[Session, Depends(get_session)]


def _iso_utc(value: datetime | None) -> str | None:
    return value.replace(tzinfo=UTC).isoformat() if value else None


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str
    enabled: bool
    last_fetched_at: datetime | None
    last_status: str | None

    @field_serializer("last_fetched_at")
    def _ser(self, value: datetime | None) -> str | None:
        return _iso_utc(value)


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    summary: str
    url: str
    published_at: datetime
    source: SourceOut
    cluster_id: str | None = None
    also_covered_by: int = 0
    event_type: str | None = None
    sectors: list[str] = Field(default_factory=list)

    @field_serializer("published_at")
    def _ser(self, value: datetime) -> str | None:
        return _iso_utc(value)


class ArticlePage(BaseModel):
    items: list[ArticleOut]
    has_more: bool


def _to_article_out(article: Article, also_covered_by: int = 0) -> ArticleOut:
    out = ArticleOut.model_validate(article)
    out.also_covered_by = max(0, also_covered_by)
    if article.tag is not None:
        out.event_type = article.tag.event_type
        out.sectors = article.tag.sectors
    return out


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/sources")
def list_sources(session: SessionDep) -> list[SourceOut]:
    return list(session.scalars(select(Source).order_by(Source.category, Source.name)))


@app.get("/api/articles")
def list_articles(
    session: SessionDep,
    category: str | None = None,
    source_id: int | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    event_type: Annotated[str | None, Query(max_length=50)] = None,
    sector: Annotated[str | None, Query(max_length=50)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
    group: bool = False,
) -> ArticlePage:
    if group:
        group_key = func.coalesce(Article.cluster_id, cast(Article.id, String))
        sub = select(
            Article.id.label("article_id"),
            func.count().over(partition_by=group_key).label("cnt"),
            func.row_number()
            .over(
                partition_by=group_key,
                order_by=(Article.published_at.desc(), Article.id.desc()),
            )
            .label("rn"),
        )
        if category:
            sub = sub.join(Article.source).where(Source.category == category)
        if source_id:
            sub = sub.where(Article.source_id == source_id)
        if q and q.strip():
            sub = sub.where(Article.title.icontains(q.strip(), autoescape=True))
        if event_type or sector:
            sub = sub.join(ArticleTag, ArticleTag.article_id == Article.id)
            if event_type:
                sub = sub.where(ArticleTag.event_type == event_type)
            if sector:
                sub = sub.where(ArticleTag.sectors_json.like(f'%"{sector}"%'))

        subq = sub.subquery()
        stmt = (
            select(Article, subq.c.cnt)
            .join(subq, Article.id == subq.c.article_id)
            .options(joinedload(Article.source), joinedload(Article.tag))
            .where(subq.c.rn == 1)
            .order_by(Article.published_at.desc(), Article.id.desc())
            .limit(limit + 1)
            .offset(offset)
        )
        rows = session.execute(stmt).all()
        items = [_to_article_out(art, cnt - 1) for art, cnt in rows[:limit]]
        return ArticlePage(items=items, has_more=len(rows) > limit)

    stmt = select(Article).options(joinedload(Article.source), joinedload(Article.tag))
    if category:
        stmt = stmt.join(Article.source).where(Source.category == category)
    if source_id:
        stmt = stmt.where(Article.source_id == source_id)
    if q and q.strip():
        stmt = stmt.where(Article.title.icontains(q.strip(), autoescape=True))
    if event_type or sector:
        stmt = stmt.join(ArticleTag, ArticleTag.article_id == Article.id)
        if event_type:
            stmt = stmt.where(ArticleTag.event_type == event_type)
        if sector:
            stmt = stmt.where(ArticleTag.sectors_json.like(f'%"{sector}"%'))
    stmt = (
        stmt.order_by(Article.published_at.desc(), Article.id.desc())
        .limit(limit + 1)
        .offset(offset)
    )
    article_rows = list(session.scalars(stmt))
    items = [_to_article_out(a) for a in article_rows[:limit]]
    return ArticlePage(items=items, has_more=len(article_rows) > limit)


def _to_notification(article: Article) -> dict:
    return {
        "id": article.id,
        "title": article.title,
        "source": article.source.name,
        "category": article.source.category,
        "url": article.url,
        "published_at": _iso_utc(article.published_at),
    }


def _fetch_notifications(
    session: Session, since_id: int, limit: int, newest_first: bool
) -> list[dict]:
    order = Article.id.desc() if newest_first else Article.id.asc()
    stmt = (
        select(Article)
        .options(joinedload(Article.source))
        .where(Article.id > since_id)
        .order_by(order)
        .limit(limit)
    )
    return [_to_notification(a) for a in session.scalars(stmt)]


def _current_max_id() -> int:
    with SessionLocal() as session:
        return session.scalar(select(func.max(Article.id))) or 0


def _fetch_new(since_id: int) -> list[dict]:
    with SessionLocal() as session:
        return _fetch_notifications(session, since_id, 50, newest_first=False)


@app.get("/api/notifications")
def notifications(session: SessionDep, limit: Annotated[int, Query(ge=1, le=50)] = 10) -> dict:
    """Newest-first notification items for the initial panel, plus the current max id."""
    items = _fetch_notifications(session, 0, limit, newest_first=True)
    return {"items": items, "latest_id": items[0]["id"] if items else 0}


@app.get("/api/stream")
async def stream(request: Request, since_id: Annotated[int, Query(ge=0)] = 0) -> StreamingResponse:
    """Server-Sent Events: pushes each new article (id > since_id) as it is ingested."""

    async def event_generator() -> AsyncIterator[str]:
        last_id = since_id or await asyncio.to_thread(_current_max_id)
        while not await request.is_disconnected():
            for row in await asyncio.to_thread(_fetch_new, last_id):
                last_id = row["id"]
                yield f"event: article\ndata: {json.dumps(row, ensure_ascii=False)}\n\n"
            yield ": keepalive\n\n"
            await asyncio.sleep(settings.sse_poll_seconds)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
