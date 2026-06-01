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
    """When Groq + Cerebras are exhausted, the remaining tiers are still tried."""
    async with LLMClient() as client:
        client.quota.mark_exhausted(Provider.GROQ)
        client.quota.mark_exhausted(Provider.CEREBRAS)

        providers = client._pick_providers()
        assert providers == [Provider.OPENROUTER, Provider.GEMINI, Provider.MISTRAL]


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


# --- Task 2+: hardened fallback (transient throttle vs terminal exhaust) ---
from pipeline.classifier.llm import (  # noqa: E402
    LLMError,
    ProviderExhaustedError,
    ProviderThrottledError,
)


@pytest.mark.asyncio
async def test_throttle_retry_recovers_then_succeeds(monkeypatch):
    """A transient throttle is retried on the SAME provider and succeeds; not exhausted."""

    async def _no_sleep(_):
        return None

    monkeypatch.setattr("pipeline.classifier.llm.asyncio.sleep", _no_sleep)

    calls = {"n": 0}

    async def fake_call(provider, *a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ProviderThrottledError("transient", retry_after=0.01)
        return {"signals": []}

    client = LLMClient()
    monkeypatch.setattr(client, "_call_provider", fake_call)
    try:
        result = await client.classify("sys", "user")
    finally:
        await client.close()
    assert result == {"signals": []}
    assert calls["n"] == 2
    assert not client.quota.is_exhausted(Provider.GROQ)


@pytest.mark.asyncio
async def test_throttle_budget_spent_switches_provider(monkeypatch):
    """Persistent throttle on provider 1 exhausts its budget → exhausted → provider 2 answers."""

    async def _no_sleep(_):
        return None

    monkeypatch.setattr("pipeline.classifier.llm.asyncio.sleep", _no_sleep)

    seen = []

    async def fake_call(provider, *a, **k):
        seen.append(provider)
        if provider == Provider.GROQ:
            raise ProviderThrottledError("always throttled", retry_after=0.0)
        return {"ok": provider.value}

    client = LLMClient()
    monkeypatch.setattr(client, "_call_provider", fake_call)
    try:
        result = await client.classify("sys", "user")
    finally:
        await client.close()

    from pipeline.config import settings

    assert seen.count(Provider.GROQ) == settings.throttle_retry_max_attempts
    assert client.quota.is_exhausted(Provider.GROQ)
    assert result != {"ok": "groq"}


@pytest.mark.asyncio
async def test_exhausted_error_switches_immediately(monkeypatch):
    """A ProviderExhaustedError switches on the FIRST round-trip (no retries)."""

    async def _no_sleep(_):
        return None

    monkeypatch.setattr("pipeline.classifier.llm.asyncio.sleep", _no_sleep)

    seen = []

    async def fake_call(provider, *a, **k):
        seen.append(provider)
        if provider == Provider.GROQ:
            raise ProviderExhaustedError("model gone")
        return {"ok": provider.value}

    client = LLMClient()
    monkeypatch.setattr(client, "_call_provider", fake_call)
    try:
        await client.classify("sys", "user")
    finally:
        await client.close()
    assert seen.count(Provider.GROQ) == 1
    assert client.quota.is_exhausted(Provider.GROQ)


@pytest.mark.asyncio
async def test_all_providers_down_raises_llmerror(monkeypatch):
    async def _no_sleep(_):
        return None

    monkeypatch.setattr("pipeline.classifier.llm.asyncio.sleep", _no_sleep)

    async def fake_call(provider, *a, **k):
        raise ProviderExhaustedError("down")

    client = LLMClient()
    monkeypatch.setattr(client, "_call_provider", fake_call)
    try:
        with pytest.raises(LLMError):
            await client.classify("sys", "user")
    finally:
        await client.close()


# --- Task 3: shared OpenAI-compatible helper (Cerebras/OpenRouter/Mistral) ---
def _http_response(status, *, json_body=None, text="", headers=None):
    req = httpx.Request("POST", "https://x.test/v1/chat/completions")
    if json_body is not None:
        return httpx.Response(status, request=req, json=json_body, headers=headers or {})
    return httpx.Response(status, request=req, text=text, headers=headers or {})


@pytest.mark.asyncio
async def test_cerebras_404_model_exhausts_immediately():
    """A 404 model_not_found raises ProviderExhaustedError in ONE round-trip."""
    from unittest.mock import AsyncMock

    client = LLMClient()
    client._http.post = AsyncMock(
        return_value=_http_response(
            404,
            json_body={
                "message": "Model x does not exist or you do not have access to it.",
                "code": "model_not_found",
            },
        )
    )
    try:
        with pytest.raises(ProviderExhaustedError):
            await client._call_cerebras("sys", "user", None)
        assert client._http.post.await_count == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_cerebras_429_is_throttle(monkeypatch):
    async def _no_sleep(_):
        return None

    monkeypatch.setattr("pipeline.classifier.llm.asyncio.sleep", _no_sleep)
    from unittest.mock import AsyncMock

    client = LLMClient()
    client._http.post = AsyncMock(
        return_value=_http_response(
            429, json_body={"message": "queue_exceeded"}, headers={"retry-after": "2"}
        )
    )
    try:
        with pytest.raises(ProviderThrottledError) as ei:
            await client._call_cerebras("sys", "user", None)
        assert ei.value.retry_after == 2.0
    finally:
        await client.close()


# --- Task 4: Gemini 429 body parsing (PerMinute vs PerDay) ---
@pytest.mark.asyncio
async def test_gemini_per_minute_429_is_throttle(monkeypatch):
    monkeypatch.setattr("pipeline.config.settings.gemini_api_key", "k", raising=False)
    from unittest.mock import AsyncMock

    client = LLMClient()
    body = {
        "error": {
            "code": 429,
            "status": "RESOURCE_EXHAUSTED",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                    "violations": [
                        {"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}
                    ],
                },
                {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "21s"},
            ],
        }
    }
    client._http.post = AsyncMock(return_value=_http_response(429, json_body=body))
    try:
        with pytest.raises(ProviderThrottledError) as ei:
            await client._call_gemini("sys", "user")
        assert ei.value.retry_after == 21.0
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_gemini_per_day_429_is_exhausted(monkeypatch):
    monkeypatch.setattr("pipeline.config.settings.gemini_api_key", "k", raising=False)
    from unittest.mock import AsyncMock

    client = LLMClient()
    body = {
        "error": {
            "code": 429,
            "status": "RESOURCE_EXHAUSTED",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                    "violations": [
                        {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}
                    ],
                }
            ],
        }
    }
    client._http.post = AsyncMock(return_value=_http_response(429, json_body=body))
    try:
        with pytest.raises(ProviderExhaustedError):
            await client._call_gemini("sys", "user")
    finally:
        await client.close()


# --- Task 5: OpenRouter + Mistral tiers ---
@pytest.mark.asyncio
async def test_openrouter_empty_completion_is_throttle(monkeypatch):
    monkeypatch.setattr("pipeline.config.settings.openrouter_api_key", "k", raising=False)

    async def _no_sleep(_):
        return None

    monkeypatch.setattr("pipeline.classifier.llm.asyncio.sleep", _no_sleep)
    from unittest.mock import AsyncMock

    client = LLMClient()
    client._http.post = AsyncMock(
        return_value=_http_response(200, json_body={"choices": [{"message": {"content": ""}}]})
    )
    try:
        with pytest.raises(ProviderThrottledError):
            await client._call_openrouter("sys", "user", None)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_openrouter_happy_path(monkeypatch):
    monkeypatch.setattr("pipeline.config.settings.openrouter_api_key", "k", raising=False)

    async def _no_sleep(_):
        return None

    monkeypatch.setattr("pipeline.classifier.llm.asyncio.sleep", _no_sleep)
    from unittest.mock import AsyncMock

    client = LLMClient()
    client._http.post = AsyncMock(
        return_value=_http_response(
            200, json_body={"choices": [{"message": {"content": '{"signals": []}'}}]}
        )
    )
    try:
        assert await client._call_openrouter("sys", "user", None) == {"signals": []}
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_mistral_happy_path(monkeypatch):
    monkeypatch.setattr("pipeline.config.settings.mistral_api_key", "k", raising=False)

    async def _no_sleep(_):
        return None

    monkeypatch.setattr("pipeline.classifier.llm.asyncio.sleep", _no_sleep)
    from unittest.mock import AsyncMock

    client = LLMClient()
    client._http.post = AsyncMock(
        return_value=_http_response(
            200, json_body={"choices": [{"message": {"content": '{"signals": []}'}}]}
        )
    )
    try:
        assert await client._call_mistral("sys", "user", None) == {"signals": []}
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_pick_providers_full_order():
    client = LLMClient()
    try:
        assert client._pick_providers() == [
            Provider.GROQ,
            Provider.OPENROUTER,
            Provider.GEMINI,
            Provider.MISTRAL,
            Provider.CEREBRAS,
        ]
    finally:
        await client.close()


# --- Review fixes: failover must not be defeated by 4xx / malformed / null bodies ---
@pytest.mark.asyncio
async def test_cerebras_null_content_is_throttle(monkeypatch):
    async def _no_sleep(_):
        return None

    monkeypatch.setattr("pipeline.classifier.llm.asyncio.sleep", _no_sleep)
    from unittest.mock import AsyncMock

    client = LLMClient()
    client._http.post = AsyncMock(
        return_value=_http_response(200, json_body={"choices": [{"message": {"content": None}}]})
    )
    try:
        with pytest.raises(ProviderThrottledError):
            await client._call_cerebras("sys", "user", None)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_openai_compat_4xx_non_model_is_exhausted():
    """A 401/403/400 (not a missing-model error) exhausts-for-run, not bubbles uncaught."""
    from unittest.mock import AsyncMock

    client = LLMClient()
    client._http.post = AsyncMock(
        return_value=_http_response(401, json_body={"error": "invalid api key"})
    )
    try:
        with pytest.raises(ProviderExhaustedError):
            await client._call_cerebras("sys", "user", None)
        assert client._http.post.await_count == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_openai_compat_malformed_body_is_exhausted():
    from unittest.mock import AsyncMock

    client = LLMClient()
    client._http.post = AsyncMock(
        return_value=_http_response(200, json_body={"unexpected": "shape"})
    )
    try:
        with pytest.raises(ProviderExhaustedError):
            await client._call_cerebras("sys", "user", None)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_openai_compat_non_json_content_is_exhausted():
    from unittest.mock import AsyncMock

    client = LLMClient()
    client._http.post = AsyncMock(
        return_value=_http_response(
            200, json_body={"choices": [{"message": {"content": "not json at all"}}]}
        )
    )
    try:
        with pytest.raises(ProviderExhaustedError):
            await client._call_cerebras("sys", "user", None)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_classify_marks_exhausted_on_unhandled_exception(monkeypatch):
    """An unexpected error (not Throttled/Exhausted) must mark the provider exhausted,
    so it is not retried on every subsequent batch of the run."""

    async def _no_sleep(_):
        return None

    monkeypatch.setattr("pipeline.classifier.llm.asyncio.sleep", _no_sleep)
    seen = []

    async def fake_call(provider, *a, **k):
        seen.append(provider)
        if provider == Provider.GROQ:
            raise ValueError("totally unexpected")
        return {"ok": provider.value}

    client = LLMClient()
    monkeypatch.setattr(client, "_call_provider", fake_call)
    try:
        await client.classify("sys", "user")
    finally:
        await client.close()
    assert client.quota.is_exhausted(Provider.GROQ)
    assert seen.count(Provider.GROQ) == 1


@pytest.mark.asyncio
async def test_gemini_4xx_non_429_is_exhausted(monkeypatch):
    monkeypatch.setattr("pipeline.config.settings.gemini_api_key", "k", raising=False)
    from unittest.mock import AsyncMock

    client = LLMClient()
    client._http.post = AsyncMock(
        return_value=_http_response(400, json_body={"error": {"message": "bad request"}})
    )
    try:
        with pytest.raises(ProviderExhaustedError):
            await client._call_gemini("sys", "user")
    finally:
        await client.close()
