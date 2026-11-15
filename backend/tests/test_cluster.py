from datetime import UTC, datetime, timedelta
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.cluster import (
    DEFAULT_SIMILARITY_THRESHOLD,
    assign_cluster_id,
    find_matching_cluster,
    normalize_title_tokens,
    token_set_similarity,
)
from app.db import Base, get_session
from app.ingest import store_entries
from app.main import app
from app.models import Article, Source


def test_normalize_title_tokens_basic():
    title = "Sensex plunges 800 pts amid global sell-off; Nifty below 24,000"
    tokens = normalize_title_tokens(title)
    # Stop words "amid", "below" filtered; 800 pts normalized to 800pts
    assert "sensex" in tokens
    assert "plunges" in tokens
    assert "800pts" in tokens
    assert "global" in tokens
    assert "nifty" in tokens
    assert "24" in tokens or "24000" in tokens
    assert "amid" not in tokens


def test_token_set_similarity_identical_and_disjoint():
    tokens_a = {"sensex", "crashes", "800pts", "nifty"}
    tokens_b = {"sensex", "crashes", "800pts", "nifty"}
    assert token_set_similarity(tokens_a, tokens_b) == 1.0

    tokens_c = {"gold", "prices", "record", "high"}
    assert token_set_similarity(tokens_a, tokens_c) == 0.0

    assert token_set_similarity(set(), set()) == 1.0
    assert token_set_similarity(tokens_a, set()) == 0.0


def test_same_story_clusters_together():
    """Two headlines covering the same story across different publications must land in the same cluster."""
    h1 = "Sensex plunges 800 pts amid global sell-off; Nifty below 24,000"
    h2 = "Sensex crashes 800 points on global cues, Nifty slips below 24,000"

    cluster_id_1 = "cluster-sensex-drop"
    recent = [(cluster_id_1, h1)]

    matched = find_matching_cluster(h2, recent, threshold=DEFAULT_SIMILARITY_THRESHOLD)
    assert matched == cluster_id_1

    assigned = assign_cluster_id(h2, recent, threshold=DEFAULT_SIMILARITY_THRESHOLD)
    assert assigned == cluster_id_1


def test_different_stories_do_not_cluster():
    """Distinct stories in the market must receive different cluster IDs."""
    h1 = "HDFC Bank Q3 net profit rises 33% to Rs 16,372 crore"
    h2 = "Tata Motors shares hit fresh 52-week high after Jaguar Land Rover sales jump"

    recent = [("cluster-hdfc", h1)]
    matched = find_matching_cluster(h2, recent, threshold=DEFAULT_SIMILARITY_THRESHOLD)
    assert matched is None

    assigned = assign_cluster_id(h2, recent, threshold=DEFAULT_SIMILARITY_THRESHOLD)
    assert assigned != "cluster-hdfc"
    assert len(assigned) == 32  # valid hex uuid


def test_store_entries_assigns_cluster_ids():
    """Ingestion pipeline assigns clusters to new articles."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as session:
        src = Source(name="Economic Times", url="https://et.indiatimes.com/rss", category="news")
        session.add(src)
        session.commit()

        entries = [
            {
                "link": "https://et.indiatimes.com/news/1",
                "title": "RBI keeps repo rate unchanged at 6.5% for 10th consecutive meeting",
                "published_parsed": (2026, 11, 14, 10, 0, 0, 4, 318, 0),
                "summary": "RBI Governor Shaktikanta Das announced monetary policy.",
            },
            {
                "link": "https://et.indiatimes.com/news/2",
                "title": "RBI monetary policy: Repo rate held steady at 6.5%",
                "published_parsed": (2026, 11, 14, 10, 5, 0, 4, 318, 0),
                "summary": "Central bank keeps interest rates on hold.",
            },
            {
                "link": "https://et.indiatimes.com/news/3",
                "title": "Gold price hits fresh high of Rs 78,000 per 10 grams in Delhi",
                "published_parsed": (2026, 11, 14, 11, 0, 0, 4, 318, 0),
                "summary": "Gold prices surged amid festive demand.",
            },
        ]

        added = store_entries(session, src, entries)
        session.commit()
        assert added == 3

        articles = session.query(Article).order_by(Article.id).all()
        assert len(articles) == 3
        # RBI articles should be in the same cluster
        assert articles[0].cluster_id is not None
        assert articles[1].cluster_id is not None
        assert articles[0].cluster_id == articles[1].cluster_id
        # Gold article in a different cluster
        assert articles[2].cluster_id is not None
        assert articles[2].cluster_id != articles[0].cluster_id


@pytest.fixture
def test_db_session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    with TestingSessionLocal() as session:
        src1 = Source(id=1, name="Mint", url="https://livemint.com/rss", category="news")
        src2 = Source(id=2, name="BusinessLine", url="https://thehindubusinessline.com/rss", category="news")
        session.add_all([src1, src2])
        session.commit()

        now = datetime.now(UTC).replace(tzinfo=None)
        # Cluster A: 3 articles
        cid_a = "cluster-a"
        a1 = Article(
            id=1,
            source_id=1,
            url="https://mint.com/1",
            url_hash="h1",
            title="Sensex plunges 800 points on global cues",
            summary="S1",
            published_at=now - timedelta(hours=3),
            fetched_at=now,
            cluster_id=cid_a,
        )
        a2 = Article(
            id=2,
            source_id=2,
            url="https://bl.com/2",
            url_hash="h2",
            title="Sensex crashes 800 pts amid global sell-off",
            summary="S2",
            published_at=now - timedelta(hours=2),
            fetched_at=now,
            cluster_id=cid_a,
        )
        a3 = Article(
            id=3,
            source_id=1,
            url="https://mint.com/3",
            url_hash="h3",
            title="Market crash: Sensex drops 800 pts, Nifty slips",
            summary="S3",
            published_at=now - timedelta(hours=1),
            fetched_at=now,
            cluster_id=cid_a,
        )

        # Cluster B: 1 article
        cid_b = "cluster-b"
        b1 = Article(
            id=4,
            source_id=2,
            url="https://bl.com/4",
            url_hash="h4",
            title="Rupee strengthens 5 paise against US dollar",
            summary="S4",
            published_at=now - timedelta(minutes=30),
            fetched_at=now,
            cluster_id=cid_b,
        )

        # Unclustered article: cluster_id is None
        c1 = Article(
            id=5,
            source_id=1,
            url="https://mint.com/5",
            url_hash="h5",
            title="SEBI issues consultation paper on derivatives",
            summary="S5",
            published_at=now - timedelta(minutes=10),
            fetched_at=now,
            cluster_id=None,
        )

        session.add_all([a1, a2, a3, b1, c1])
        session.commit()

    return TestingSessionLocal


def test_api_articles_ungrouped_behavior(test_db_session_factory):
    """When group is False (default), all 5 articles are returned with also_covered_by=0."""
    def override_get_session():
        with test_db_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)
        res = client.get("/api/articles")
        assert res.status_code == 200
        data = res.json()
        assert len(data["items"]) == 5
        for item in data["items"]:
            assert item["also_covered_by"] == 0

        # With explicit group=false
        res_explicit = client.get("/api/articles?group=false")
        assert res_explicit.status_code == 200
        assert len(res_explicit.json()["items"]) == 5
    finally:
        app.dependency_overrides.clear()


def test_api_articles_grouped_behavior(test_db_session_factory):
    """When group=true, returns one row per cluster with also_covered_by count."""
    def override_get_session():
        with test_db_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)
        res = client.get("/api/articles?group=true")
        assert res.status_code == 200
        data = res.json()
        items = data["items"]

        # 3 distinct groups: Cluster A, Cluster B, and Unclustered C
        assert len(items) == 3

        # Order should be newest first:
        # 1. SEBI (unclustered, id=5, newest) -> also_covered_by = 0
        # 2. Rupee (Cluster B, id=4) -> also_covered_by = 0
        # 3. Market crash (Cluster A, newest row id=3) -> also_covered_by = 2 (3 articles in cluster - 1)
        assert items[0]["id"] == 5
        assert items[0]["also_covered_by"] == 0

        assert items[1]["id"] == 4
        assert items[1]["also_covered_by"] == 0

        assert items[2]["id"] == 3
        assert items[2]["also_covered_by"] == 2
        assert items[2]["cluster_id"] == "cluster-a"
    finally:
        app.dependency_overrides.clear()
