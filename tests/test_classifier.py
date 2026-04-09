"""Integration tests for the classifier (uses real API calls)."""

import pytest

from pipeline.classifier.categorizer import (
    Category,
    ClassifiedSignal,
    classify_signals,
)
from pipeline.classifier.llm import LLMClient, Provider

pytestmark = pytest.mark.integration

SAMPLE_SIGNALS = [
    {
        "source": "McCain Foods",
        "title": "McCain Foods Launches Precision Agriculture Supplier Program",
        "content": (
            "McCain Foods announced today a new supplier program aimed at "
            "integrating precision agriculture technologies across its network "
            "of 300+ potato growers in the United States. The program will "
            "evaluate yield monitoring and variable rate application tools "
            "from multiple vendors starting Q3 2026."
        ),
    },
    {
        "source": "Lamb Weston",
        "title": "Lamb Weston Expands Processing Capacity in Idaho",
        "content": (
            "Lamb Weston Holdings announced a $200M investment to expand its "
            "potato processing facility in American Falls, Idaho. The expansion "
            "will increase french fry production capacity by 350 million pounds "
            "annually and is expected to be completed by mid-2027."
        ),
    },
    {
        "source": "Bayer Crop Science",
        "title": "Bayer Partners with AgTech Startup on Data Integration",
        "content": (
            "Bayer Crop Science today announced a strategic partnership with "
            "FarmTech Analytics to integrate third-party sensor data into its "
            "Climate FieldView platform. The partnership will allow farmers to "
            "connect any yield monitor to FieldView, regardless of brand."
        ),
    },
]


@pytest.mark.asyncio
async def test_classify_batch_groq():
    """Test batch classification with Groq (primary provider)."""
    async with LLMClient() as client:
        results = await classify_signals(client, SAMPLE_SIGNALS)

    assert len(results) == 3
    for r in results:
        assert isinstance(r, ClassifiedSignal)
        assert r.category in Category
        assert 1 <= r.relevance_score <= 5
        assert len(r.summary) > 20
        assert isinstance(r.entities.companies, list)

    # Signal 1 should be high relevance (vendor search / precision ag)
    assert results[0].relevance_score >= 4
    # Signal 3 (Bayer + yield monitor) should score high
    assert results[2].relevance_score >= 3

    print("\n--- Groq Classification Results ---")
    for i, r in enumerate(results):
        print(f"\nSignal {i + 1}: {r.category.value} (score {r.relevance_score})")
        print(f"  Summary: {r.summary}")
        print(f"  Entities: {r.entities.model_dump()}")


@pytest.mark.asyncio
async def test_classify_batch_cerebras():
    """Test batch classification with Cerebras (fallback)."""
    async with LLMClient() as client:
        # Force Cerebras by marking Groq as exhausted
        client.quota.mark_exhausted(Provider.GROQ)
        results = await classify_signals(client, SAMPLE_SIGNALS[:2])

    assert len(results) == 2
    for r in results:
        assert isinstance(r, ClassifiedSignal)
        assert r.category in Category

    print("\n--- Cerebras Classification Results ---")
    for i, r in enumerate(results):
        print(f"\nSignal {i + 1}: {r.category.value} (score {r.relevance_score})")
        print(f"  Summary: {r.summary}")


@pytest.mark.asyncio
async def test_quota_tracking():
    """Test that request usage is tracked across calls."""
    async with LLMClient() as client:
        await classify_signals(client, SAMPLE_SIGNALS[:1])

    total_used = sum(client.quota.requests_used.values())
    assert total_used >= 1
