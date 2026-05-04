"""Integration test: verify Groq→Cerebras fallback on rate limit."""

import httpx
import pytest

from pipeline.classifier.categorizer import ClassifiedSignal, classify_signals
from pipeline.classifier.llm import LLMClient, Provider, QuotaState, _retry_on_5xx

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


@pytest.mark.integration
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


@pytest.mark.integration
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


def _make_http_status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.test/x")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(f"{status}", request=request, response=response)


@pytest.mark.asyncio
async def test_retry_on_5xx_recovers_after_transient_503(monkeypatch):
    """A 503 followed by a 200 should yield the 200 result without raising."""

    # Make sleep instant so the test runs fast.
    async def _no_sleep(_):
        return None

    monkeypatch.setattr("pipeline.classifier.llm.asyncio.sleep", _no_sleep)

    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        if calls["n"] == 1:
            raise _make_http_status_error(503)
        return {"ok": True}

    result = await _retry_on_5xx(factory, label="test")
    assert result == {"ok": True}
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_retry_on_5xx_exhausts_after_max_attempts(monkeypatch):
    """Persistent 503 should raise after max_attempts."""

    async def _no_sleep(_):
        return None

    monkeypatch.setattr("pipeline.classifier.llm.asyncio.sleep", _no_sleep)

    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        raise _make_http_status_error(503)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await _retry_on_5xx(factory, label="test", max_attempts=3)
    assert exc_info.value.response.status_code == 503
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_retry_on_5xx_does_not_retry_4xx(monkeypatch):
    """A 429 must propagate immediately (caller maps it to ProviderExhaustedError)."""

    async def _no_sleep(_):
        return None

    monkeypatch.setattr("pipeline.classifier.llm.asyncio.sleep", _no_sleep)

    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        raise _make_http_status_error(429)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await _retry_on_5xx(factory, label="test")
    assert exc_info.value.response.status_code == 429
    assert calls["n"] == 1


def test_quota_header_check_cerebras_tokens_minute():
    """Cerebras-specific tokens-minute header must trigger switch at 90%."""
    quota = QuotaState()
    headers = {
        "x-ratelimit-remaining-tokens-minute": "5000",
        "x-ratelimit-limit-tokens-minute": "60000",
    }
    quota.check_headers(Provider.CEREBRAS, headers)
    assert quota.is_exhausted(Provider.CEREBRAS)


@pytest.mark.asyncio
async def test_call_cerebras_sleeps_after_success(monkeypatch):
    """After a successful Cerebras call, the client must sleep to throttle RPM."""
    from unittest.mock import AsyncMock

    sleeps: list[float] = []

    async def _record_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("pipeline.classifier.llm.asyncio.sleep", _record_sleep)

    client = LLMClient()
    try:
        # Mock the underlying HTTP post to return a valid Cerebras response.
        mock_response = httpx.Response(
            200,
            request=httpx.Request("POST", "https://api.cerebras.ai/v1/chat/completions"),
            json={"choices": [{"message": {"content": '{"signals": []}'}}]},
        )
        client._http.post = AsyncMock(return_value=mock_response)

        await client._call_cerebras("sys", "user", json_schema=None)
    finally:
        await client.close()

    # The throttle sleep must have happened with the configured delay.
    from pipeline.config import settings as _settings

    assert _settings.cerebras_inter_call_delay in sleeps
