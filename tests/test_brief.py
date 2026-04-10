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
    """Should return None if no signals meet threshold."""
    raw = [_raw("Test", "content")]
    cls = [_cls("other", 0, "Static page")]
    result = await generate_brief(raw, cls, target_types=["customer"], min_score=3)
    assert result is None


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
    cls = [_cls("product_launch", 3, f"Signal {i}") for i in range(10)]
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
