import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .provider import LLMProvider

log = logging.getLogger(__name__)

IMPACT_EVENT_TYPES = frozenset({"policy", "govt_capex", "commodity", "flows"})

DIRECTIONS = frozenset({"up", "down", "mixed"})
Direction = Literal["up", "down", "mixed"]

HORIZONS = frozenset({"immediate", "1-4q", "multi-year"})
Horizon = Literal["immediate", "1-4q", "multi-year"]


class SectorImpact(BaseModel):
    sector: str
    direction: Direction
    why: str

    @field_validator("sector", mode="before")
    @classmethod
    def validate_sector(cls, v: object) -> str:
        s = str(v).strip()
        if not s:
            raise ValueError("sector cannot be empty")
        return s

    @field_validator("direction", mode="before")
    @classmethod
    def validate_direction(cls, v: object) -> str:
        if isinstance(v, str) and v.strip().lower() in DIRECTIONS:
            return v.strip().lower()
        raise ValueError(f"direction must be one of {sorted(DIRECTIONS)}")

    @field_validator("why", mode="before")
    @classmethod
    def validate_why(cls, v: object) -> str:
        s = str(v).strip()
        if not s:
            raise ValueError("why cannot be empty")
        return s


class ImpactResult(BaseModel):
    first_order: list[SectorImpact] = Field(min_length=1)
    second_order: list[SectorImpact] = Field(default_factory=list)
    horizon: Horizon
    confidence: float
    evidence: str

    @field_validator("horizon", mode="before")
    @classmethod
    def validate_horizon(cls, v: object) -> str:
        if isinstance(v, str) and v.strip().lower() in HORIZONS:
            return v.strip().lower()
        raise ValueError(f"horizon must be one of {sorted(HORIZONS)}")

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, v: object) -> float:
        if v is None:
            raise ValueError("confidence is required")
        if isinstance(v, (str, int, float)):
            try:
                val = float(v)
            except ValueError as exc:
                raise ValueError("confidence must be a float") from exc
        else:
            raise ValueError("confidence must be a float")
        if not (0.0 <= val <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")
        return round(val, 2)

    @field_validator("evidence", mode="before")
    @classmethod
    def validate_evidence(cls, v: object) -> str:
        s = str(v).strip()
        if not s:
            raise ValueError("evidence is required and cannot be empty")
        return s


IMPACT_SYSTEM_PROMPT = """You are an Indian financial market analyst analyzing policy,
government capex, commodity, and capital flow developments.
Your task is to infer first-order and second-order transmission channels to market sectors.

Public product → informational only. Describe impact ("this affects sector X").
NEVER give buy/sell calls or stock recommendations (SEBI compliance).

Respond ONLY with a valid JSON object matching this schema:
{
  "first_order": [
    {"sector": "<sector_name>", "direction": "up|down|mixed", "why": "<concise reason>"}
  ],
  "second_order": [
    {"sector": "<sector_name>", "direction": "up|down|mixed", "why": "<indirect effect>"}
  ],
  "horizon": "immediate|1-4q|multi-year",
  "confidence": <float between 0.0 and 1.0>,
  "evidence": "<specific factual quote or data point from the article>"
}

Definitions:
- first_order: Direct beneficiaries or impacted sectors (e.g. road budget -> Infrastructure).
  At least one required.
- second_order: Indirect, downstream beneficiaries or casualties (e.g. infra capex -> Cement).
  Can be empty [] if none.
- direction: strictly one of "up" (beneficiary), "down" (headwind), "mixed" (divergent).
- horizon: strictly one of "immediate" (days/weeks), "1-4q" (1 to 4 quarters), "multi-year".
- confidence: float between 0.0 and 1.0 based on how clearly text supports the channel. Required.
- evidence: concise quote or factual reference from text supporting the analysis. Required.
- Return RAW JSON only. Do not wrap in markdown or add explanations."""


def build_impact_user_prompt(
    title: str,
    summary: str = "",
    event_type: str = "",
    sectors: list[str] | None = None,
) -> str:
    lines = [f"Headline: {title}"]
    if summary and summary != title:
        lines.append(f"Summary: {summary}")
    if event_type:
        lines.append(f"Event Type: {event_type}")
    if sectors:
        lines.append(f"Tagged Sectors: {', '.join(sectors)}")
    return "\n".join(lines)


def parse_impact_response(raw_text: str) -> ImpactResult | None:
    """Parse and strictly validate LLM impact output.

    Drops invalid output and logs a warning; returns None on any failure.
    """
    if not raw_text or not raw_text.strip():
        log.warning("Empty response received for impact analysis")
        return None

    text = raw_text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()

    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            log.warning("Impact JSON is not an object: %s", raw_text[:200])
            return None
        return ImpactResult.model_validate(data)
    except Exception as exc:
        log.warning("Failed to parse LLM impact output: %s (error: %s)", raw_text[:200], exc)
        return None


def analyze_impact(
    provider: LLMProvider,
    title: str,
    summary: str = "",
    event_type: str = "",
    sectors: list[str] | None = None,
) -> ImpactResult | None:
    """Run impact inference for policy/capex/commodity/flows articles.

    Returns ImpactResult if successful, or None on failure or invalid output.
    Never crashes ingestion.
    """
    if event_type not in IMPACT_EVENT_TYPES:
        return None
    try:
        user_prompt = build_impact_user_prompt(title, summary, event_type, sectors)
        raw_response = provider.complete(system=IMPACT_SYSTEM_PROMPT, user=user_prompt)
        return parse_impact_response(raw_response)
    except Exception as exc:
        log.warning("Impact analysis failed for '%s': %s", title[:80], exc)
        return None
