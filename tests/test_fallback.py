"""Integration test: verify Groq→Cerebras fallback on rate limit."""

import pytest

from pipeline.classifier.categorizer import ClassifiedSignal, classify_signals
from pipeline.classifier.llm import LLMClient, Provider, QuotaState

pytestmark = pytest.mark.integration

SIGNAL = [
    {
        "source": "McCain Foods",
        "title": "McCain launches precision ag program",
        "content": (
            "McCain Foods announced a new precision agriculture supplier "
            "program to evaluate yield monitoring tools from multiple vendors."
        ),
    }
]


@pytest.mark.asyncio
async def test_fallback_groq_to_cerebras():
    """Simulate Groq exhaustion, verify Cerebras handles the request."""
    async with LLMClient() as client:
        client.quota.mark_exhausted(Provider.GROQ)

        results = await classify_signals(client, SIGNAL)

    assert len(results) == 1
    assert isinstance(results[0], ClassifiedSignal)
    assert results[0].relevance_score >= 3
    assert client.quota.requests_used[Provider.GROQ] == 0
    assert client.quota.requests_used[Provider.CEREBRAS] == 1


@pytest.mark.asyncio
async def test_fallback_groq_and_cerebras_exhausted():
    """When both Groq and Cerebras are exhausted, Gemini is tried (if configured)."""
    async with LLMClient() as client:
        client.quota.mark_exhausted(Provider.GROQ)
        client.quota.mark_exhausted(Provider.CEREBRAS)

        providers = client._pick_providers()
        assert providers == [Provider.GEMINI]


def test_quota_header_check_triggers_switch():
    """Verify that 90%+ usage in headers marks provider as exhausted."""
    quota = QuotaState()
    headers = {
        "x-ratelimit-remaining-tokens": "5000",
        "x-ratelimit-limit-tokens": "100000",
    }
    quota.check_headers(Provider.GROQ, headers)
    assert quota.is_exhausted(Provider.GROQ)


def test_quota_header_check_no_switch_below_threshold():
    """Below 90% usage, provider should not be marked exhausted."""
    quota = QuotaState()
    headers = {
        "x-ratelimit-remaining-tokens": "50000",
        "x-ratelimit-limit-tokens": "100000",
    }
    quota.check_headers(Provider.GROQ, headers)
    assert not quota.is_exhausted(Provider.GROQ)


def test_quota_header_check_requests_and_tokens():
    """Token limit hit even if requests are fine should trigger switch."""
    quota = QuotaState()
    headers = {
        "x-ratelimit-remaining-requests": "500",
        "x-ratelimit-limit-requests": "1000",
        "x-ratelimit-remaining-tokens-day": "8000",
        "x-ratelimit-limit-tokens-day": "100000",
    }
    quota.check_headers(Provider.GROQ, headers)
    assert quota.is_exhausted(Provider.GROQ)
