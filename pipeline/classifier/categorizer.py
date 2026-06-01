"""Signal classification using multi-provider LLM client."""

import logging
from enum import StrEnum

from pydantic import BaseModel, Field

from pipeline.classifier.llm import LLMClient
from pipeline.classifier.prompts import SYSTEM_PROMPT, format_batch_prompt

logger = logging.getLogger(__name__)


class Category(StrEnum):
    PRECISION_AG_ADOPTION = "precision_ag_adoption"
    SUSTAINABILITY_INITIATIVE = "sustainability_initiative"
    TECH_INVESTMENT = "tech_investment"
    VENDOR_SEARCH = "vendor_search"
    EXPANSION = "expansion"
    LEADERSHIP_CHANGE = "leadership_change"
    PARTNERSHIP = "partnership"
    FUNDING_M_AND_A = "funding_m_and_a"
    PRODUCT_LAUNCH = "product_launch"
    MARKET_MOVE = "market_move"
    OTHER = "other"


class EntityList(BaseModel):
    companies: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)

    @classmethod
    def coerce(cls, v):
        """Handle LLMs returning entities as a flat list instead of a dict."""
        if isinstance(v, list):
            return cls(companies=v)
        if isinstance(v, dict):
            return cls(**v)
        return cls()


class ClassifiedSignal(BaseModel):
    category: Category
    relevance_score: int = Field(ge=0, le=5)
    summary: str
    entities: EntityList = Field(default_factory=EntityList)

    @classmethod
    def from_raw(cls, data: dict) -> "ClassifiedSignal":
        """Parse with lenient entity handling."""
        data = dict(data)
        data["entities"] = EntityList.coerce(data.get("entities", {}))
        return cls(**data)


class BatchClassification(BaseModel):
    signals: list[ClassifiedSignal]


CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "signals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": [c.value for c in Category],
                    },
                    "relevance_score": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 5,
                    },
                    "summary": {"type": "string"},
                    "entities": {
                        "type": "object",
                        "properties": {
                            "companies": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "people": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "products": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["companies", "people", "products"],
                    },
                },
                "required": [
                    "category",
                    "relevance_score",
                    "summary",
                    "entities",
                ],
            },
        }
    },
    "required": ["signals"],
}


async def classify_signals(
    client: LLMClient,
    raw_signals: list[dict],
    target_types: list[str] | None = None,
) -> list[ClassifiedSignal | None]:
    """Classify a batch of raw signals.

    Returns a list ALIGNED 1:1 with ``raw_signals``: index ``i`` holds the
    classification for ``raw_signals[i]``, or ``None`` if that item could not
    be validated. Position-preserving so callers can zip signals to
    classifications without misalignment, even when the LLM drops, reorders,
    or over-produces items.
    """
    user_prompt = format_batch_prompt(raw_signals, target_types)

    result = await client.classify(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        json_schema=CLASSIFICATION_SCHEMA,
    )

    raw_items = result.get("signals", [])
    aligned: list[ClassifiedSignal | None] = []
    for i in range(len(raw_signals)):
        item = raw_items[i] if i < len(raw_items) else None
        if item is None:
            aligned.append(None)
            continue
        try:
            aligned.append(ClassifiedSignal.from_raw(item))
        except Exception:
            aligned.append(None)

    n_ok = sum(1 for c in aligned if c is not None)
    if n_ok != len(raw_signals):
        logger.warning(f"Classified {n_ok}/{len(raw_signals)} signals (rest dropped)")

    return aligned
