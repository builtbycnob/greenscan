"""Tests for brief generator (mock LLM, no API calls)."""

from unittest.mock import AsyncMock, patch

import pytest

from pipeline.brief.generator import _format_signals_for_brief, generate_brief
from pipeline.classifier.categorizer import ClassifiedSignal, EntityList
from pipeline.scraper.models import RawSignal


def _raw(source: str, content: str) -> RawSignal:
    return RawSignal(url="https://test.com", title="Test", content=content, source=source)


def _cls(category: str, score: int, summary: str) -> ClassifiedSignal:
    return ClassifiedSignal(
        category=category,
        relevance_score=score,
        summary=summary,
        entities=EntityList(),
    )


def test_format_signals_customer():
    raw = [_raw("McCain", "content")]
    cls = [_cls("vendor_search", 5, "McCain launches program")]
    cust_text, comp_text = _format_signals_for_brief(raw, cls, ["customer"])
    assert "vendor_search" in cust_text
    assert "McCain" in cust_text
    assert "5/5" in cust_text
    assert comp_text == ""


def test_format_signals_competitor():
    raw = [_raw("Trimble", "content")]
    cls = [_cls("product_launch", 4, "Trimble launches sensor")]
    cust_text, comp_text = _format_signals_for_brief(raw, cls, ["competitor"])
    assert "Trimble" in comp_text
    assert cust_text == ""


def test_format_signals_mixed():
    raw = [_raw("McCain", "a"), _raw("Deere", "b")]
    cls = [
        _cls("vendor_search", 5, "McCain program"),
        _cls("product_launch", 4, "Deere sensor"),
    ]
    cust_text, comp_text = _format_signals_for_brief(raw, cls, ["customer", "competitor"])
    assert "McCain" in cust_text
    assert "Deere" in comp_text


@pytest.mark.asyncio
async def test_brief_skips_low_score():
    """Should return None if no signals meet threshold (score 0)."""
    raw = [_raw("Test", "content")]
    cls = [_cls("other", 0, "Static page")]
    result = await generate_brief(raw, cls, target_types=["customer"])
    assert result is None


@pytest.mark.asyncio
async def test_brief_excludes_score_one_customers():
    """Score-1 customer signals are noise and should not appear in the brief."""
    raw = [_raw("NoiseCo", "noise content"), _raw("GoodCo", "good content")]
    cls = [
        _cls("other", 1, "Noise signal"),
        _cls("vendor_search", 3, "Real opportunity"),
    ]
    types = ["customer", "customer"]

    with patch(
        "pipeline.brief.generator._generate_with_groq",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = "# Brief"
        await generate_brief(raw, cls, target_types=types)

    call_args = mock.call_args[0][0]
    assert "Real opportunity" in call_args
    assert "Noise signal" not in call_args


@pytest.mark.asyncio
async def test_brief_filters_by_score():
    """Should only include signals at or above min_score."""
    raw = [_raw("A", "a"), _raw("B", "b"), _raw("C", "c")]
    cls = [
        _cls("other", 0, "Static"),
        _cls("vendor_search", 5, "High"),
        _cls("expansion", 3, "Medium"),
    ]
    types = ["customer", "customer", "customer"]

    with patch(
        "pipeline.brief.generator._generate_with_groq",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = "# Brief"
        result = await generate_brief(raw, cls, target_types=types)

    assert result == "# Brief"
    call_args = mock.call_args[0][0]
    assert "High" in call_args
    assert "Medium" in call_args
    assert "Static" not in call_args


@pytest.mark.asyncio
async def test_brief_caps_competitor_signals():
    """Competitor signals should be capped at competitor_signals_cap."""
    raw = [_raw(f"Comp{i}", f"content{i}") for i in range(10)]
    # Score 4 to clear the new competitor floor (4).
    cls = [_cls("product_launch", 4, f"Signal {i}") for i in range(10)]
    types = ["competitor"] * 10

    with patch(
        "pipeline.brief.generator._generate_with_groq",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = "# Brief"
        await generate_brief(raw, cls, target_types=types)

    call_args = mock.call_args[0][0]
    # Default cap is 5
    assert call_args.count("--- Signal ---") <= 5


@pytest.mark.asyncio
async def test_brief_enforces_total_signal_cap():
    """Total signals (customer + competitor) must respect brief_max_total_signals."""
    from pipeline.config import settings

    # 30 customer signals, all above threshold — should be capped at the
    # total budget once competitors are subtracted.
    raw = [_raw(f"Cust{i}", f"content{i}") for i in range(30)]
    cls = [_cls("vendor_search", 5, f"Customer signal {i}") for i in range(30)]
    types = ["customer"] * 30

    with patch(
        "pipeline.brief.generator._generate_with_groq",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = "# Brief"
        await generate_brief(raw, cls, target_types=types)

    call_args = mock.call_args[0][0]
    assert call_args.count("--- Signal ---") <= settings.brief_max_total_signals


@pytest.mark.asyncio
async def test_brief_contacts_survive_filtering():
    """Contacts keyed by content_hash survive after low-score signals are filtered out."""
    # Signal A: score 0 (filtered out), Signal B: score 5 (kept)
    raw_a = _raw("LowCo", "low score content aaa")
    raw_b = _raw("HighCo", "high score content bbb")
    cls_a = _cls("other", 0, "Static")
    cls_b = _cls("vendor_search", 5, "Big opportunity")

    # Contacts keyed by content_hash of signal B
    class FakeContact:
        name = "Jane Doe"
        headline = "VP Sales"
        linkedin_url = "https://linkedin.com/in/jane"
        source = "signal_mention"

    contacts = {raw_b.content_hash: [FakeContact()]}

    with patch(
        "pipeline.brief.generator._generate_with_groq",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = "# Brief"
        await generate_brief(
            [raw_a, raw_b],
            [cls_a, cls_b],
            target_types=["customer", "customer"],
            contacts=contacts,
        )

    call_args = mock.call_args[0][0]
    # Signal A filtered out, signal B kept, contacts for B survive
    assert "Jane Doe" in call_args
    assert "HighCo" in call_args
    assert "Static" not in call_args
