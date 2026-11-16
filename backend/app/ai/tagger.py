import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .provider import LLMProvider

log = logging.getLogger(__name__)

EVENT_TYPES = (
    "policy",
    "govt_capex",
    "commodity",
    "flows",
    "earnings",
    "corporate_action",
    "macro",
    "other",
)
EventType = Literal[
    "policy",
    "govt_capex",
    "commodity",
    "flows",
    "earnings",
    "corporate_action",
    "macro",
    "other",
]


class TagResult(BaseModel):
    sector: list[str] = Field(default_factory=list)
    event_type: EventType = "other"
    companies: list[str] = Field(default_factory=list)

    @field_validator("event_type", mode="before")
    @classmethod
    def validate_event_type(cls, v: object) -> str:
        if isinstance(v, str):
            clean_v = v.strip().lower()
            if clean_v in EVENT_TYPES:
                return clean_v
        return "other"

    @field_validator("sector", "companies", mode="before")
    @classmethod
    def ensure_str_list(cls, v: object) -> list[str]:
        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]
        if isinstance(v, str) and v.strip():
            return [v.strip()]
        return []


TAG_SYSTEM_PROMPT = """You are an Indian financial market analyst classifying news articles.
Respond ONLY with a valid JSON object matching this schema:
{
  "sector": ["<sector_name>", ...],
  "event_type": "<one allowed event_type>",
  "companies": ["<company_name_or_ticker>", ...]
}

Guidelines:
- sector: Indian market sectors impacted (e.g. Banking, IT, Auto, Energy, FMCG,
  Pharma, Metals, Infrastructure, Real Estate, Telecom, Defence). Empty list [] if macro.
- event_type: strictly one of: policy, govt_capex, commodity, flows, earnings,
  corporate_action, macro, other.
- companies: mentioned listed companies or major entities (e.g. HDFC Bank, Reliance,
  Tata Motors, Infosys). Empty list [] if none.
- Return RAW JSON only. Do not wrap in markdown or add explanation."""


def build_tag_user_prompt(title: str, summary: str) -> str:
    text = f"Headline: {title}"
    if summary and summary != title:
        text += f"\nSummary: {summary}"
    return text


def parse_tag_response(raw_text: str) -> TagResult:
    """Parse and validate LLM output. On any failure, return TagResult(event_type='other')."""
    if not raw_text or not raw_text.strip():
        return TagResult(event_type="other")

    text = raw_text.strip()
    # Strip markdown code blocks if present (```json ... ``` or ``` ... ```)
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return TagResult.model_validate(data)
    except Exception as exc:
        log.warning("Failed to parse LLM tagging output: %s (error: %s)", raw_text[:200], exc)

    return TagResult(event_type="other")


def tag_article(provider: LLMProvider, title: str, summary: str = "") -> TagResult:
    """Classify an article using the LLMProvider. Never crashes ingestion on error."""
    try:
        user_prompt = build_tag_user_prompt(title, summary)
        raw_response = provider.complete(system=TAG_SYSTEM_PROMPT, user=user_prompt)
        return parse_tag_response(raw_response)
    except Exception as exc:
        log.warning("Tagging invocation failed for '%s': %s", title[:80], exc)
        return TagResult(event_type="other")
