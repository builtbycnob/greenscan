"""Tests for contact discovery (mocked Serper, no API calls)."""

from unittest.mock import AsyncMock, patch

import pytest

from pipeline.classifier.categorizer import ClassifiedSignal, EntityList
from pipeline.enrichment.contacts import ContactResult, discover_contacts


def _cls(score: int, people: list[str] | None = None) -> ClassifiedSignal:
    entities = EntityList(
        companies=["TestCo"],
        people=people or [],
        products=[],
    )
    return ClassifiedSignal(
        category="vendor_search",
        relevance_score=score,
        summary="Test signal",
        entities=entities,
    )


def test_contact_result_format_signal_mention():
    c = ContactResult(
        name="John Smith",
        headline="VP Agronomy - McCain",
        linkedin_url="https://linkedin.com/in/john",
        source="signal_mention",
    )
    formatted = c.format_for_brief()
    assert "John Smith" in formatted
    assert "🔍" not in formatted
    assert "linkedin.com" in formatted


def test_contact_result_format_company_lookup():
    c = ContactResult(
        name="Jane Doe",
        headline="CEO",
        linkedin_url="https://linkedin.com/in/jane",
        source="company_lookup",
    )
    formatted = c.format_for_brief()
    assert "🔍" in formatted


@pytest.mark.asyncio
async def test_discover_skips_competitors():
    """Should not look up contacts for competitor signals."""
    classified = [_cls(5, ["Bob CEO"])]
    types = ["competitor"]
    sources = ["Trimble"]

    with patch("pipeline.enrichment.contacts.settings") as mock_settings:
        mock_settings.serper_api_key = "test"
        mock_settings.serper_daily_contact_cap = 20
        mock_settings.contact_min_score = 3
        result = await discover_contacts(classified, types, sources)

    assert result == {}


@pytest.mark.asyncio
async def test_discover_skips_low_score():
    """Should not look up contacts for low-score signals."""
    classified = [_cls(1)]
    types = ["customer"]
    sources = ["McCain"]

    with patch("pipeline.enrichment.contacts.settings") as mock_settings:
        mock_settings.serper_api_key = "test"
        mock_settings.serper_daily_contact_cap = 20
        mock_settings.contact_min_score = 3
        result = await discover_contacts(classified, types, sources)

    assert result == {}


@pytest.mark.asyncio
async def test_discover_with_named_person():
    """Should search LinkedIn for named people in signal."""
    classified = [_cls(5, ["John Smith, VP Agronomy"])]
    types = ["customer"]
    sources = ["McCain"]
    keys = ["hash_abc123"]

    mock_contact = {
        "name": "John Smith",
        "headline": "VP Agronomy - McCain Foods",
        "linkedin_url": "https://linkedin.com/in/john-smith",
    }

    with (
        patch("pipeline.enrichment.contacts.settings") as mock_settings,
        patch(
            "pipeline.enrichment.contacts.search_linkedin_contact",
            new_callable=AsyncMock,
            return_value=mock_contact,
        ),
    ):
        mock_settings.serper_api_key = "test"
        mock_settings.serper_daily_contact_cap = 20
        mock_settings.contact_min_score = 3
        result = await discover_contacts(classified, types, sources, signal_keys=keys)

    assert "hash_abc123" in result
    assert result["hash_abc123"][0].name == "John Smith"
    assert result["hash_abc123"][0].source == "signal_mention"


@pytest.mark.asyncio
async def test_discover_company_lookup_fallback():
    """Should search for company leaders when no people mentioned."""
    classified = [_cls(5)]  # No people
    types = ["customer"]
    sources = ["McCain"]
    keys = ["hash_xyz789"]
    titles = {"McCain": ["VP Agronomy", "CEO"]}

    mock_leaders = [
        {
            "name": "Jane Doe",
            "headline": "VP Agronomy - McCain",
            "linkedin_url": "https://linkedin.com/in/jane",
        }
    ]

    with (
        patch("pipeline.enrichment.contacts.settings") as mock_settings,
        patch(
            "pipeline.enrichment.contacts.search_company_leaders",
            new_callable=AsyncMock,
            return_value=mock_leaders,
        ),
    ):
        mock_settings.serper_api_key = "test"
        mock_settings.serper_daily_contact_cap = 20
        mock_settings.contact_min_score = 3
        result = await discover_contacts(
            classified, types, sources, signal_keys=keys, decision_maker_titles=titles
        )

    assert "hash_xyz789" in result
    assert result["hash_xyz789"][0].name == "Jane Doe"
    assert result["hash_xyz789"][0].source == "company_lookup"
