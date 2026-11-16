import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.provider import FakeProvider, LLMProvider
from app.ai.tagger import TagResult, parse_tag_response, tag_article
from app.db import Base, get_session
from app.ingest import store_entries
from app.main import app
from app.models import Article, ArticleTag, Source

# --- parsing / validation (pure) ---


def test_parse_valid_json():
    raw = json.dumps({"sector": ["Banking"], "event_type": "policy", "companies": ["HDFC Bank"]})
    result = parse_tag_response(raw)
    assert result.event_type == "policy"
    assert result.sector == ["Banking"]
    assert result.companies == ["HDFC Bank"]


def test_parse_strips_markdown_fence():
    raw = '```json\n{"sector": ["IT"], "event_type": "earnings", "companies": []}\n```'
    result = parse_tag_response(raw)
    assert result.event_type == "earnings"
    assert result.sector == ["IT"]


def test_parse_unknown_event_type_becomes_other():
    raw = json.dumps({"sector": ["Auto"], "event_type": "merger_rumour", "companies": []})
    result = parse_tag_response(raw)
    assert result.event_type == "other"
    assert result.sector == ["Auto"]


def test_parse_garbage_degrades_to_other():
    assert parse_tag_response("not json at all").event_type == "other"
    assert parse_tag_response("").event_type == "other"
    # a JSON array (non-dict) must not crash
    assert parse_tag_response("[1, 2, 3]").event_type == "other"


def test_parse_coerces_messy_lists():
    raw = json.dumps({"sector": "Banking", "event_type": "POLICY", "companies": [" SBI ", ""]})
    result = parse_tag_response(raw)
    assert result.event_type == "policy"  # case-insensitive
    assert result.sector == ["Banking"]  # scalar coerced to list
    assert result.companies == ["SBI"]  # trimmed, blanks dropped


# --- tag_article via provider ---


def test_tag_article_with_fake_provider():
    canned = json.dumps(
        {"sector": ["Metals"], "event_type": "commodity", "companies": ["Tata Steel"]}
    )
    provider = FakeProvider(canned_response=canned)
    result = tag_article(provider, "Steel prices surge", "Global demand lifts metals")
    assert result.event_type == "commodity"
    assert result.sector == ["Metals"]
    assert len(provider.calls) == 1


class _BoomProvider(LLMProvider):
    def complete(self, system: str, user: str) -> str:
        raise RuntimeError("model unavailable")


def test_tag_article_never_crashes_on_provider_error():
    result = tag_article(_BoomProvider(), "Some headline")
    assert isinstance(result, TagResult)
    assert result.event_type == "other"


# --- ingestion wiring ---


def test_store_entries_tags_new_articles():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine)
    canned = json.dumps({"sector": ["Banking"], "event_type": "policy", "companies": ["HDFC Bank"]})
    with Session() as session:
        source = Source(name="ET", url="https://et.test/rss", category="news")
        session.add(source)
        session.commit()
        entries = [
            {"link": "https://et.test/1", "title": "RBI holds repo rate", "summary": "policy"}
        ]
        added = store_entries(
            session, source, entries, provider=FakeProvider(canned_response=canned)
        )
        session.commit()
        assert added == 1
        article = session.query(Article).one()
        assert article.tag is not None
        assert article.tag.event_type == "policy"
        assert article.tag.sectors == ["Banking"]
        assert article.tag.companies == ["HDFC Bank"]


# --- API filters ---


@pytest.fixture
def tagged_session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC).replace(tzinfo=None)
    with Session() as session:
        src = Source(id=1, name="ET", url="https://et.test/rss", category="news")
        session.add(src)
        session.flush()

        def make(aid: int, title: str, event_type: str | None, sectors: list[str]):
            art = Article(
                id=aid,
                source_id=1,
                url=f"https://et.test/{aid}",
                url_hash=f"h{aid}",
                title=title,
                summary="",
                published_at=now - timedelta(minutes=aid),
                fetched_at=now,
            )
            if event_type is not None:
                art.tag = ArticleTag(
                    event_type=event_type,
                    sectors_json=json.dumps(sectors),
                    companies_json="[]",
                    created_at=now,
                )
            session.add(art)

        make(1, "RBI policy update", "policy", ["Banking"])
        make(2, "Infosys Q3 results", "earnings", ["IT"])
        make(3, "Untagged market note", None, [])
        session.commit()
    return Session


def _client(factory):
    def override():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = override
    return TestClient(app)


def test_filter_by_event_type(tagged_session_factory):
    try:
        res = _client(tagged_session_factory).get("/api/articles?event_type=policy")
        assert res.status_code == 200
        items = res.json()["items"]
        assert [i["id"] for i in items] == [1]
        assert items[0]["event_type"] == "policy"
        assert items[0]["sectors"] == ["Banking"]
    finally:
        app.dependency_overrides.clear()


def test_filter_by_sector(tagged_session_factory):
    try:
        res = _client(tagged_session_factory).get("/api/articles?sector=IT")
        assert res.status_code == 200
        items = res.json()["items"]
        assert [i["id"] for i in items] == [2]
    finally:
        app.dependency_overrides.clear()


def test_unfiltered_includes_untagged_and_exposes_tags(tagged_session_factory):
    try:
        res = _client(tagged_session_factory).get("/api/articles")
        assert res.status_code == 200
        items = {i["id"]: i for i in res.json()["items"]}
        assert set(items) == {1, 2, 3}
        assert items[1]["event_type"] == "policy"
        assert items[3]["event_type"] is None  # untagged article still returned
        assert items[3]["sectors"] == []
    finally:
        app.dependency_overrides.clear()
