import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.impact import (
    IMPACT_EVENT_TYPES,
    analyze_impact,
    parse_impact_response,
)
from app.ai.provider import FakeProvider
from app.db import Base, get_session
from app.ingest import store_entries
from app.main import app
from app.models import Article, ArticleImpact, ArticleTag, Source

# --- parsing / validation (pure) ---


def test_parse_valid_impact_json():
    raw = json.dumps(
        {
            "first_order": [
                {
                    "sector": "Infrastructure",
                    "direction": "up",
                    "why": "National highway budget increased by 20%",
                }
            ],
            "second_order": [
                {
                    "sector": "Cement",
                    "direction": "up",
                    "why": "Higher road construction drives bulk cement consumption",
                }
            ],
            "horizon": "1-4q",
            "confidence": 0.85,
            "evidence": "Govt allocates Rs 2.7 lakh crore for road transport and highways",
        }
    )
    result = parse_impact_response(raw)
    assert result is not None
    assert len(result.first_order) == 1
    assert result.first_order[0].sector == "Infrastructure"
    assert result.first_order[0].direction == "up"
    assert len(result.second_order) == 1
    assert result.second_order[0].sector == "Cement"
    assert result.horizon == "1-4q"
    assert result.confidence == 0.85
    assert "2.7 lakh crore" in result.evidence


def test_parse_strips_markdown_fence():
    raw = (
        "```json\n"
        '{"first_order": [{"sector": "Auto", "direction": "down", "why": "Steel price hike"}],'
        ' "second_order": [], "horizon": "immediate", "confidence": 0.70,'
        ' "evidence": "Steel up 5%"}\n```'
    )
    result = parse_impact_response(raw)
    assert result is not None
    assert result.first_order[0].sector == "Auto"
    assert result.first_order[0].direction == "down"
    assert result.horizon == "immediate"
    assert result.confidence == 0.70


def test_parse_missing_confidence_rejected():
    raw = json.dumps(
        {
            "first_order": [{"sector": "Banking", "direction": "mixed", "why": "Rate pause"}],
            "horizon": "immediate",
            "evidence": "RBI leaves repo rate unchanged at 6.5%",
        }
    )
    assert parse_impact_response(raw) is None


def test_parse_invalid_confidence_rejected():
    # Out of range (> 1.0 or < 0.0)
    raw_high = json.dumps(
        {
            "first_order": [{"sector": "Banking", "direction": "up", "why": "Rate cut"}],
            "horizon": "immediate",
            "confidence": 1.5,
            "evidence": "RBI cuts repo rate by 25 bps",
        }
    )
    assert parse_impact_response(raw_high) is None

    raw_neg = json.dumps(
        {
            "first_order": [{"sector": "Banking", "direction": "up", "why": "Rate cut"}],
            "horizon": "immediate",
            "confidence": -0.1,
            "evidence": "RBI cuts repo rate by 25 bps",
        }
    )
    assert parse_impact_response(raw_neg) is None

    # String confidence
    raw_str = json.dumps(
        {
            "first_order": [{"sector": "Banking", "direction": "up", "why": "Rate cut"}],
            "horizon": "immediate",
            "confidence": "high",
            "evidence": "RBI cuts repo rate by 25 bps",
        }
    )
    assert parse_impact_response(raw_str) is None


def test_parse_invalid_direction_rejected():
    raw = json.dumps(
        {
            "first_order": [{"sector": "Banking", "direction": "bullish", "why": "Positive"}],
            "horizon": "1-4q",
            "confidence": 0.8,
            "evidence": "RBI maintains status quo",
        }
    )
    assert parse_impact_response(raw) is None


def test_parse_invalid_horizon_rejected():
    raw = json.dumps(
        {
            "first_order": [{"sector": "Metals", "direction": "up", "why": "Tariff imposed"}],
            "horizon": "short-term",
            "confidence": 0.8,
            "evidence": "Import duty hiked to 15%",
        }
    )
    assert parse_impact_response(raw) is None


def test_parse_missing_evidence_rejected():
    raw = json.dumps(
        {
            "first_order": [{"sector": "Metals", "direction": "up", "why": "Tariff imposed"}],
            "horizon": "1-4q",
            "confidence": 0.8,
            "evidence": "",
        }
    )
    assert parse_impact_response(raw) is None


def test_parse_empty_first_order_rejected():
    raw = json.dumps(
        {
            "first_order": [],
            "second_order": [{"sector": "Power", "direction": "up", "why": "Coal supply"}],
            "horizon": "1-4q",
            "confidence": 0.75,
            "evidence": "Coal India increases supply",
        }
    )
    assert parse_impact_response(raw) is None


def test_parse_garbage_and_non_dict_rejected():
    assert parse_impact_response("not json at all") is None
    assert parse_impact_response("") is None
    assert parse_impact_response("   ") is None
    assert parse_impact_response("[1, 2, 3]") is None


def test_analyze_impact_skips_non_impact_event_types():
    provider = FakeProvider(canned_response="{}")
    for event_type in ("earnings", "corporate_action", "macro", "other"):
        assert event_type not in IMPACT_EVENT_TYPES
        res = analyze_impact(provider, "Title", "Summary", event_type=event_type)
        assert res is None
    # No calls made
    assert len(provider.calls) == 0


def test_analyze_impact_calls_provider_for_eligible_types():
    canned = json.dumps(
        {
            "first_order": [{"sector": "Metals", "direction": "down", "why": "Export tax"}],
            "second_order": [],
            "horizon": "immediate",
            "confidence": 0.9,
            "evidence": "Govt levies 15% export duty on iron ore pellets",
        }
    )
    provider = FakeProvider(canned_response=canned)

    for event_type in ("policy", "govt_capex", "commodity", "flows"):
        res = analyze_impact(
            provider,
            "Iron ore export duty",
            "Govt levies export duty",
            event_type=event_type,
            sectors=["Metals"],
        )
        assert res is not None
        assert res.first_order[0].sector == "Metals"
        assert res.confidence == 0.9

    assert len(provider.calls) == 4


# --- database / ingestion / API integration ---


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sm = sessionmaker(bind=engine)
    with sm() as session:
        src = Source(name="Mint", url="https://livemint.com/rss", category="markets", enabled=True)
        session.add(src)
        session.commit()
    yield sm
    Base.metadata.drop_all(engine)


def test_store_entries_creates_impact_for_policy_article(test_db):
    tag_resp = json.dumps(
        {
            "sector": ["Infrastructure"],
            "event_type": "policy",
            "companies": ["L&T"],
        }
    )
    impact_resp = json.dumps(
        {
            "first_order": [
                {
                    "sector": "Infrastructure",
                    "direction": "up",
                    "why": "New dedicated freight corridor approved",
                }
            ],
            "second_order": [
                {
                    "sector": "Logistics",
                    "direction": "up",
                    "why": "Faster transit speeds reduce operating costs",
                }
            ],
            "horizon": "multi-year",
            "confidence": 0.92,
            "evidence": "Cabinet approves Rs 30,000 cr freight corridor project",
        }
    )

    def fake_complete(system: str, user: str) -> str:
        if "infer first-order and second-order" in system:
            return impact_resp
        return tag_resp

    provider = FakeProvider(canned_response=fake_complete)

    with test_db() as session:
        src = session.scalar(select(Source))
        entries = [
            {
                "link": "https://livemint.com/freight-corridor",
                "title": "Cabinet approves Rs 30,000 cr freight corridor project",
                "summary": "Cabinet committee approves dedicated freight corridor.",
                "published_parsed": (2026, 11, 16, 10, 0, 0, 0, 0, 0),
            }
        ]
        inserted = store_entries(session, src, entries, provider=provider)
        session.commit()

        assert inserted == 1
        art = session.scalar(select(Article).where(Article.title.like("%freight%")))
        assert art is not None
        assert art.tag is not None
        assert art.tag.event_type == "policy"

        assert art.impact is not None
        assert len(art.impact.first_order) == 1
        assert art.impact.first_order[0]["sector"] == "Infrastructure"
        assert art.impact.first_order[0]["direction"] == "up"
        assert len(art.impact.second_order) == 1
        assert art.impact.second_order[0]["sector"] == "Logistics"
        assert art.impact.horizon == "multi-year"
        assert art.impact.confidence == 0.92
        assert "30,000 cr" in art.impact.evidence


def test_store_entries_drops_malformed_impact_without_crashing(test_db):
    tag_resp = json.dumps({"sector": ["Commodity"], "event_type": "commodity", "companies": []})
    malformed_impact = "not a valid json output from model"

    def fake_complete(system: str, user: str) -> str:
        if "infer first-order and second-order" in system:
            return malformed_impact
        return tag_resp

    provider = FakeProvider(canned_response=fake_complete)

    with test_db() as session:
        src = session.scalar(select(Source))
        entries = [
            {
                "link": "https://livemint.com/crude-oil-surge",
                "title": "Brent crude surges 4% amid Middle East tensions",
                "summary": "Crude oil benchmarks rally on supply concerns.",
                "published_parsed": (2026, 11, 16, 11, 0, 0, 0, 0, 0),
            }
        ]
        inserted = store_entries(session, src, entries, provider=provider)
        session.commit()

        assert inserted == 1
        art = session.scalar(select(Article).where(Article.title.like("%Brent crude%")))
        assert art is not None
        assert art.tag is not None
        assert art.tag.event_type == "commodity"
        # Impact was dropped due to invalid JSON, article still saved!
        assert art.impact is None


def test_get_impact_endpoint(test_db):
    now = datetime.now(UTC).replace(tzinfo=None)
    with test_db() as session:
        src = session.scalar(select(Source))
        art = Article(
            source_id=src.id,
            url="https://livemint.com/pli-scheme",
            url_hash="pli_scheme_hash_1",
            title="Govt expands PLI scheme for IT hardware",
            summary="Ministry announces additional incentives.",
            published_at=now,
            fetched_at=now,
        )
        session.add(art)
        session.flush()

        art.tag = ArticleTag(
            event_type="govt_capex",
            sectors_json=json.dumps(["IT", "Electronics"]),
            companies_json=json.dumps(["Dixon Technologies"]),
            created_at=now,
        )
        art.impact = ArticleImpact(
            first_order_json=json.dumps(
                [
                    {
                        "sector": "Electronics",
                        "direction": "up",
                        "why": "Direct incentive payouts lower domestic manufacturing cost",
                    }
                ]
            ),
            second_order_json=json.dumps(
                [
                    {
                        "sector": "IT",
                        "direction": "up",
                        "why": "Better availability of local hardware assemblies",
                    }
                ]
            ),
            horizon="1-4q",
            confidence=0.88,
            evidence="Additional outlay of Rs 5,000 crore approved under PLI",
            created_at=now,
        )
        session.commit()
        article_id = art.id

    client = TestClient(app)
    app.dependency_overrides[get_session] = lambda: test_db()

    try:
        # 1. Successful fetch
        resp = client.get(f"/api/impacts?article_id={article_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["article_id"] == article_id
        assert len(data["first_order"]) == 1
        assert data["first_order"][0]["sector"] == "Electronics"
        assert data["first_order"][0]["direction"] == "up"
        assert data["horizon"] == "1-4q"
        assert data["confidence"] == 0.88
        assert "5,000 crore" in data["evidence"]

        # 2. 404 for non-existent article
        resp_404 = client.get("/api/impacts?article_id=999999")
        assert resp_404.status_code == 404
        assert resp_404.json()["detail"] == "Impact record not found"

        # 3. 422 for missing article_id parameter
        resp_422 = client.get("/api/impacts")
        assert resp_422.status_code == 422

        # 4. GET /api/articles exposes has_impact flag
        art_resp = client.get("/api/articles")
        assert art_resp.status_code == 200
        items = art_resp.json()["items"]
        assert len(items) == 1
        assert items[0]["has_impact"] is True
    finally:
        app.dependency_overrides.clear()
