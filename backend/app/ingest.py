import calendar
import hashlib
import html
import json
import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .cluster import assign_cluster_id
from .config import settings
from .db import SessionLocal
from .models import Article, Source

log = logging.getLogger(__name__)

SUMMARY_MAX_CHARS = 300
_TRACKING_PARAMS = re.compile(r"^(utm_|fbclid$|gclid$)")
_TAGS = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")
IST = timezone(timedelta(hours=5, minutes=30))
# RBI omits the zone (times are IST); SEBI sends date-only values. feedparser rejects both.
_FALLBACK_DATE_FORMATS = ("%a, %d %b %Y %H:%M:%S", "%d %b, %Y %z")


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = urlencode(
        [(k, v) for k, v in parse_qsl(parts.query) if not _TRACKING_PARAMS.match(k.lower())]
    )
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, "")
    )


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode()).hexdigest()


def clean_text(raw: str, max_chars: int | None = None) -> str:
    text = _WHITESPACE.sub(" ", html.unescape(_TAGS.sub(" ", raw or ""))).strip()
    if max_chars and len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "…"
    return text


def parse_published(entry: Any, now: datetime) -> datetime:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime.fromtimestamp(calendar.timegm(parsed), UTC).replace(tzinfo=None)
    raw = (entry.get("published") or entry.get("updated") or "").strip()
    for fmt in _FALLBACK_DATE_FORMATS:
        try:
            value = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        if value.tzinfo is None:
            value = value.replace(tzinfo=IST)
        return value.astimezone(UTC).replace(tzinfo=None)
    return now


@dataclass
class FetchResult:
    status: str
    entries: list = field(default_factory=list)
    etag: str | None = None
    last_modified: str | None = None


def fetch_feed(
    client: httpx.Client, url: str, etag: str | None, last_modified: str | None
) -> FetchResult:
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    try:
        response = client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        return FetchResult(
            status=f"error: {type(exc).__name__}", etag=etag, last_modified=last_modified
        )
    if response.status_code == 304:
        return FetchResult(status="not modified", etag=etag, last_modified=last_modified)
    if response.status_code != 200:
        return FetchResult(
            status=f"error: HTTP {response.status_code}", etag=etag, last_modified=last_modified
        )
    parsed = feedparser.parse(response.content)
    if not parsed.entries:
        return FetchResult(
            status="error: no entries parsed", etag=etag, last_modified=last_modified
        )
    return FetchResult(
        status="ok",
        entries=parsed.entries,
        etag=response.headers.get("ETag"),
        last_modified=response.headers.get("Last-Modified"),
    )


def store_entries(session: Session, source: Source, entries: list) -> int:
    now = utcnow()
    candidates: dict[str, Article] = {}
    for entry in entries:
        link = entry.get("link")
        title = clean_text(entry.get("title", ""))
        if not link or not title:
            continue
        published = parse_published(entry, now)
        summary = clean_text(entry.get("summary", ""), SUMMARY_MAX_CHARS)
        candidates.setdefault(
            url_hash(link),
            Article(
                source_id=source.id,
                url=link.strip(),
                url_hash=url_hash(link),
                title=title[:1000],
                summary="" if summary == title else summary,
                published_at=min(published, now),
                fetched_at=now,
            ),
        )
    if not candidates:
        return 0
    existing = set(
        session.scalars(select(Article.url_hash).where(Article.url_hash.in_(candidates)))
    )
    new = [article for key, article in candidates.items() if key not in existing]
    if not new:
        return 0

    three_days_ago = now - timedelta(days=3)
    recent = list(
        session.scalars(
            select(Article).where(
                Article.published_at >= three_days_ago,
            )
        )
    )
    recent_clusters: list[tuple[str, str]] = []
    for art in recent:
        if not art.cluster_id:
            art.cluster_id = uuid.uuid4().hex
        recent_clusters.append((art.cluster_id, art.title))

    for article in new:
        cid = assign_cluster_id(article.title, recent_clusters)
        article.cluster_id = cid
        recent_clusters.append((cid, article.title))

    session.add_all(new)
    return len(new)


def sync_sources(session: Session) -> None:
    feeds = json.loads(settings.feeds_file.read_text(encoding="utf-8"))
    by_url = {s.url: s for s in session.scalars(select(Source))}
    for feed in feeds:
        source = by_url.get(feed["url"])
        if source is None:
            source = Source(url=feed["url"])
            session.add(source)
        source.name = feed["name"]
        source.category = feed["category"]
        source.enabled = feed.get("enabled", True)
    listed = {feed["url"] for feed in feeds}
    for url, source in by_url.items():
        if url not in listed:
            source.enabled = False
    session.commit()


def run_ingest() -> dict[str, int]:
    """Fetch every enabled source once. Returns new-article counts by source name."""
    counts: dict[str, int] = {}
    with SessionLocal() as session:
        sources = list(session.scalars(select(Source).where(Source.enabled)))
        with (
            httpx.Client(
                timeout=settings.http_timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": settings.user_agent},
            ) as client,
            ThreadPoolExecutor(max_workers=8) as pool,
        ):
            results = list(
                pool.map(lambda s: fetch_feed(client, s.url, s.etag, s.last_modified), sources)
            )
        for source, result in zip(sources, results, strict=True):
            added = store_entries(session, source, result.entries)
            source.etag = result.etag
            source.last_modified = result.last_modified
            source.last_fetched_at = utcnow()
            source.last_status = result.status
            session.commit()
            counts[source.name] = added
            log.info("%s: %s, %d new", source.name, result.status, added)
    return counts


if __name__ == "__main__":
    from .db import Base, engine

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        sync_sources(s)
    run_ingest()
