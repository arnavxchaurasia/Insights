import time
from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.ingest import clean_text, normalize_url, parse_published, store_entries, url_hash
from app.models import Article, Source


def test_normalize_url_strips_tracking_fragment_and_trailing_slash():
    a = normalize_url("https://Example.com/news/story/?utm_source=rss&id=7#top")
    assert a == "https://example.com/news/story?id=7"
    assert url_hash("https://example.com/news/story?id=7") == url_hash(
        "https://example.com/news/story/?id=7&utm_medium=x"
    )


def test_clean_text_strips_html_and_truncates():
    assert clean_text("<p>RBI &amp; SEBI\n  act</p>") == "RBI & SEBI act"
    out = clean_text("word " * 200, 50)
    assert len(out) <= 51 and out.endswith("…")


def test_parse_published_handles_regulator_date_formats():
    now = datetime(2030, 1, 1)
    assert parse_published({"published": "Fri, 13 Nov 2026 17:50:00"}, now) == datetime(
        2026, 11, 13, 12, 20
    )
    assert parse_published({"published": "13 Nov, 2026 +0530"}, now) == datetime(
        2026, 11, 12, 18, 30
    )
    assert parse_published({"published": "garbage"}, now) == now


def test_store_entries_deduplicates_within_and_across_batches():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        source = Source(name="t", url="https://feed.test/rss", category="news")
        session.add(source)
        session.commit()
        entry = {
            "link": "https://x.test/a",
            "title": "A",
            "summary": "<b>s</b>",
            "published_parsed": time.gmtime(0),
        }
        batch = [
            entry,
            {**entry, "link": "https://x.test/a/?utm_source=rss"},
            {"link": "https://x.test/b", "title": "B"},
        ]
        assert store_entries(session, source, batch) == 2
        session.commit()
        assert store_entries(session, source, batch) == 0
        assert len(list(session.scalars(select(Article)))) == 2
