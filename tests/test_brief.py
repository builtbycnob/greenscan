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


def test_format_signals():
    raw = [_raw("McCain", "content")]
    cls = [_cls("vendor_search", 5, "McCain launches program")]
    result = _format_signals_for_brief(raw, cls)
    assert "vendor_search" in result
    assert "McCain" in result
    assert "5/5" in result


@pytest.mark.asyncio
async def test_brief_skips_low_score():
    """Should return None if no signals meet threshold."""
    raw = [_raw("Test", "content")]
    cls = [_cls("other", 1, "Low relevance")]
    result = await generate_brief(raw, cls, min_score=3)
    assert result is None


@pytest.mark.asyncio
async def test_brief_filters_by_score():
    """Should only include signals at or above min_score."""
    raw = [_raw("A", "a"), _raw("B", "b"), _raw("C", "c")]
    cls = [
        _cls("other", 1, "Low"),
        _cls("vendor_search", 5, "High"),
        _cls("expansion", 3, "Medium"),
    ]

    with patch("pipeline.brief.generator._generate_with_groq", new_callable=AsyncMock) as mock:
        mock.return_value = "# Brief"
        result = await generate_brief(raw, cls, min_score=3)

    assert result == "# Brief"
    call_args = mock.call_args[0][0]
    assert "High" in call_args
    assert "Medium" in call_args
    assert "Low" not in call_args
