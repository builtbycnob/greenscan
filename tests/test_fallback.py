"""Integration test: verify Groq→Cerebras fallback on rate limit."""

import pytest

from pipeline.classifier.categorizer import ClassifiedSignal, classify_signals
from pipeline.classifier.llm import LLMClient, Provider

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
        # Exhaust Groq quota artificially
        client.quota.remaining_requests[Provider.GROQ] = 0

        results = await classify_signals(client, SIGNAL)

    assert len(results) == 1
    assert isinstance(results[0], ClassifiedSignal)
    assert results[0].relevance_score >= 3
    # Verify it used Cerebras (Groq was skipped)
    assert client.quota.requests_used[Provider.GROQ] == 0
    assert client.quota.requests_used[Provider.CEREBRAS] == 1


@pytest.mark.asyncio
async def test_fallback_both_exhausted_still_works():
    """When Groq and Cerebras are 'exhausted', they're still tried as last resort."""
    async with LLMClient() as client:
        client.quota.remaining_requests[Provider.GROQ] = 0
        client.quota.remaining_requests[Provider.CEREBRAS] = 0

        # Should still succeed — exhausted providers are tried as fallback
        results = await classify_signals(client, SIGNAL)
        assert len(results) == 1


@pytest.mark.asyncio
async def test_circuit_breaker_opens():
    """After 5 failures, circuit breaker should skip the provider."""
    from pipeline.classifier.llm import BREAKERS

    breaker = BREAKERS[Provider.GROQ]
    # Reset state
    breaker.fail_count = 0
    breaker.opened_at = None

    # Simulate 5 failures
    for _ in range(5):
        breaker.record_failure()

    assert breaker.is_open
    # After recording success, should close
    breaker.record_success()
    assert not breaker.is_open
