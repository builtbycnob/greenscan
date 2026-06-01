# LLM Tier Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended here — the changes are interdependent and mostly in one file) or superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the daily pipeline survive any single LLM tier vanishing, by splitting transient throttles from terminal exhaustion, parsing Gemini's 429 body, adding Mistral + OpenRouter tiers, and isolating per-batch failures so one dead batch can't abort the run.

**Architecture:** `pipeline/classifier/llm.py` gains a two-class exhaustion signal (`ProviderThrottledError` retry-same-tier vs `ProviderExhaustedError` switch) wrapped by a single `_call_with_throttle_retry` loop; Cerebras/OpenRouter/Mistral share one `_call_openai_compatible` helper; Gemini parses `error.details[].quotaId`. `pipeline/main.py` extracts a testable `_classify_in_batches` that catches `LLMError` per batch and keeps signal↔classification alignment. The brief generator gains a 3-provider fallback chain.

**Tech Stack:** Python 3.12, asyncio, httpx, groq SDK, pydantic-settings, pytest + monkeypatch/AsyncMock.

---

## File structure

| File | Responsibility | Change |
|---|---|---|
| `pipeline/config.py` | settings | + OpenRouter/Mistral keys+models, Cerebras model/delay, batch=15, throttle attempts |
| `pipeline/classifier/llm.py` | provider chain | core: exceptions, throttle-retry, shared helper, Gemini 429 parse, 2 new providers |
| `pipeline/main.py` | orchestration | extract `_classify_in_batches`, per-batch isolation + alignment |
| `pipeline/brief/generator.py` | brief | 429-aware Gemini + 3-tier fallback |
| `tests/test_fallback.py` | llm tests | + throttle/exhaust/empty/Gemini-429 tests; fix exhausted-set test |
| `tests/test_main_isolation.py` | isolation test | new |
| `tests/test_brief.py` | brief tests | + fallback-chain test |
| `scripts/probe_openrouter.py`, `scripts/probe_mistral.py`, `scripts/probe_gemini.py` | live probes | new |
| `.github/workflows/daily_pipeline.yml` | CI env | + OPENROUTER_API_KEY, MISTRAL_API_KEY |
| `RUNBOOK.md`, `docs/changelog.md`, `CLAUDE.md` | docs | reconcile |

---

## Task 1: Config additions

**Files:** Modify `pipeline/config.py`

- [ ] **Step 1: Edit config** — change `cerebras_model`, `cerebras_inter_call_delay`, `max_signals_per_batch`; add new settings.

```python
    # Live probe 2026-06-01: this account's free tier lists ONLY gpt-oss-120b
    # (production) + zai-glm-4.7 (preview); both POST 200. qwen-3-235b returns
    # 404 "no access" — delisted from the free roster (Dedicated/paid only).
    cerebras_model: str = "gpt-oss-120b"
    gemini_model: str = "gemini-2.5-flash"
    gemini_lite_model: str = "gemini-2.5-flash-lite"

    # OpenRouter (funded $10 once → 1000 RPD / 20 RPM). OpenAI-compatible.
    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    openrouter_inter_call_delay: float = 3.0  # ≤20 RPM

    # Mistral (free, no card; 1B tok/month; 2 RPM). OpenAI-compatible.
    mistral_api_key: str = ""
    mistral_model: str = "mistral-small-latest"
    mistral_inter_call_delay: float = 31.0  # ≤2 RPM

    # Cerebras free tier = 5 RPM per model → 1 call / 12s (old 6.0 ≈ 10 RPM exceeded it).
    cerebras_inter_call_delay: float = 12.0

    # Transient-throttle retry budget (per provider, per call) before switching.
    throttle_retry_max_attempts: int = 4
```
Also change `max_signals_per_batch: int = 10` → `15`.

- [ ] **Step 2: Verify import** — `uv run python -c "from pipeline.config import settings; print(settings.cerebras_model, settings.max_signals_per_batch, settings.openrouter_model, settings.mistral_model)"`
Expected: `gpt-oss-120b 15 meta-llama/llama-3.3-70b-instruct:free mistral-small-latest`

- [ ] **Step 3: Commit**
```bash
git add pipeline/config.py
git commit -m "feat(config): add OpenRouter/Mistral tiers, swap Cerebras model, batch 15"
```

---

## Task 2: Exception taxonomy + throttle-retry orchestration

**Files:** Modify `pipeline/classifier/llm.py`; Test `tests/test_fallback.py`

- [ ] **Step 1: Write failing tests** (append to `tests/test_fallback.py`)

```python
import pytest
from pipeline.classifier.llm import (
    LLMClient, Provider, ProviderThrottledError, ProviderExhaustedError, LLMError,
)


@pytest.mark.asyncio
async def test_throttle_retry_recovers_then_succeeds(monkeypatch):
    """A transient throttle on a provider is retried on the SAME provider and succeeds; provider NOT exhausted."""
    async def _no_sleep(_): return None
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
    assert not client.quota.is_exhausted(Provider.GROQ)  # first provider, recovered


@pytest.mark.asyncio
async def test_throttle_budget_spent_switches_provider(monkeypatch):
    """Persistent throttle on provider 1 exhausts its budget → marked exhausted → provider 2 answers."""
    async def _no_sleep(_): return None
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
    # GROQ tried throttle_retry_max_attempts times, then exhausted + switched.
    from pipeline.config import settings
    assert seen.count(Provider.GROQ) == settings.throttle_retry_max_attempts
    assert client.quota.is_exhausted(Provider.GROQ)
    assert result != {"ok": "groq"}


@pytest.mark.asyncio
async def test_exhausted_error_switches_immediately(monkeypatch):
    """A ProviderExhaustedError switches on the FIRST round-trip (no retries)."""
    async def _no_sleep(_): return None
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
    assert seen.count(Provider.GROQ) == 1  # NOT retried
    assert client.quota.is_exhausted(Provider.GROQ)


@pytest.mark.asyncio
async def test_all_providers_down_raises_llmerror(monkeypatch):
    async def _no_sleep(_): return None
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
```

- [ ] **Step 2: Run, expect fail** — `uv run python -m pytest tests/test_fallback.py -k "throttle or exhausted_error_switches or all_providers_down" -q`
Expected: ImportError/AttributeError (`ProviderThrottledError` not defined).

- [ ] **Step 3: Implement** in `pipeline/classifier/llm.py`. Add the exception and helper class; rewire `classify()` and `_call_provider`.

Add near `ProviderExhaustedError`:
```python
class ProviderThrottledError(Exception):
    """Transient throttle (per-minute 429 / empty completion / queue). Retry SAME provider."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after
```

Replace the `classify()` per-provider loop body and add `_call_with_throttle_retry`:
```python
        for provider in providers:
            try:
                result = await self._call_with_throttle_retry(
                    provider, system_prompt, user_prompt, json_schema
                )
                self.quota.record_use(provider)
                return result
            except ProviderExhaustedError as e:
                self.quota.mark_exhausted(provider)
                last_error = e
                continue
            except Exception as e:
                last_error = e
                logger.warning(f"{provider.value} failed: {e}")
                continue

        raise LLMError(f"All providers exhausted. Last error: {last_error}")

    async def _call_with_throttle_retry(
        self, provider: Provider, system_prompt: str, user_prompt: str, json_schema: dict | None
    ) -> dict:
        """Call a provider, retrying transient throttles on the SAME provider.

        Escalates to ProviderExhaustedError once the budget is spent so the
        caller switches providers.
        """
        attempts = settings.throttle_retry_max_attempts
        last: Exception | None = None
        for attempt in range(attempts):
            try:
                return await self._call_provider(
                    provider, system_prompt, user_prompt, json_schema
                )
            except ProviderThrottledError as e:
                last = e
                delay = e.retry_after if e.retry_after is not None else RETRY_BASE_DELAY * (2**attempt)
                logger.info(
                    f"{provider.value} throttled ({attempt + 1}/{attempts}), retry in {delay:.1f}s"
                )
                if attempt < attempts - 1:
                    await asyncio.sleep(delay)
        raise ProviderExhaustedError(
            f"{provider.value} throttled past retry budget: {last}"
        )
```

Simplify `_call_provider` to pure dispatch (remove the old 429→Exhausted mapping; each provider now raises its own signal). Groq's rate-limit mapping moves into `_call_groq`:
```python
    async def _call_provider(
        self, provider: Provider, system_prompt: str, user_prompt: str, json_schema: dict | None
    ) -> dict:
        if provider == Provider.GROQ:
            return await self._call_groq(system_prompt, user_prompt, json_schema)
        elif provider == Provider.CEREBRAS:
            return await self._call_cerebras(system_prompt, user_prompt, json_schema)
        elif provider == Provider.OPENROUTER:
            return await self._call_openrouter(system_prompt, user_prompt, json_schema)
        elif provider == Provider.MISTRAL:
            return await self._call_mistral(system_prompt, user_prompt, json_schema)
        else:
            return await self._call_gemini(system_prompt, user_prompt)
```
In `_call_groq`, wrap the SDK call:
```python
        try:
            raw = await self._groq.chat.completions.with_raw_response.create(**kwargs)
        except GroqRateLimitError as e:
            raise ProviderThrottledError(f"groq rate limited: {e}") from e
```
(NOTE: `Provider.OPENROUTER`/`MISTRAL` and `_call_openrouter`/`_call_mistral` are added in Tasks 4-5; this dispatch references them ahead of time. To keep this task green in isolation, temporarily map them to `_call_cerebras` is NOT needed — Task 2's tests monkeypatch `_call_provider`, so the real bodies aren't called. But the enum members must exist for the `elif` to import; add them in Task 1.5 below or fold the enum additions here.)

- [ ] **Step 3b: Add enum + quota members now** (so `_call_provider` references resolve). In `class Provider(StrEnum)` add:
```python
    OPENROUTER = "openrouter"
    MISTRAL = "mistral"
```
In `QuotaState.requests_used` default dict, add `Provider.OPENROUTER: 0, Provider.MISTRAL: 0,`. Leave `_pick_providers` order unchanged for now (GROQ, CEREBRAS, GEMINI) — extended in Task 5. Add stub methods so dispatch imports cleanly (real bodies in Tasks 4-5):
```python
    async def _call_openrouter(self, system_prompt, user_prompt, json_schema):
        raise ProviderExhaustedError("openrouter not configured")

    async def _call_mistral(self, system_prompt, user_prompt, json_schema):
        raise ProviderExhaustedError("mistral not configured")
```

- [ ] **Step 4: Run, expect pass** — `uv run python -m pytest tests/test_fallback.py -q`
Expected: all green (existing 11 + 4 new).

- [ ] **Step 5: Commit**
```bash
git add pipeline/classifier/llm.py tests/test_fallback.py
git commit -m "feat(llm): split transient throttle vs terminal exhaust + bounded retry"
```

---

## Task 3: Shared OpenAI-compatible helper + Cerebras via it

**Files:** Modify `pipeline/classifier/llm.py`; Test `tests/test_fallback.py`

- [ ] **Step 1: Write failing tests**
```python
def _http_response(status, *, json_body=None, text="", headers=None):
    req = httpx.Request("POST", "https://x.test/v1/chat/completions")
    if json_body is not None:
        return httpx.Response(status, request=req, json=json_body, headers=headers or {})
    return httpx.Response(status, request=req, text=text, headers=headers or {})


@pytest.mark.asyncio
async def test_cerebras_404_model_exhausts_immediately(monkeypatch):
    """A 404 model_not_found raises ProviderExhaustedError in ONE round-trip."""
    from unittest.mock import AsyncMock
    client = LLMClient()
    client._http.post = AsyncMock(return_value=_http_response(
        404, json_body={"message": "Model x does not exist or you do not have access to it.",
                        "code": "model_not_found"}))
    try:
        with pytest.raises(ProviderExhaustedError):
            await client._call_cerebras("sys", "user", None)
        assert client._http.post.await_count == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_cerebras_429_is_throttle(monkeypatch):
    async def _no_sleep(_): return None
    monkeypatch.setattr("pipeline.classifier.llm.asyncio.sleep", _no_sleep)
    from unittest.mock import AsyncMock
    client = LLMClient()
    client._http.post = AsyncMock(return_value=_http_response(
        429, json_body={"message": "queue_exceeded"}, headers={"retry-after": "2"}))
    try:
        with pytest.raises(ProviderThrottledError) as ei:
            await client._call_cerebras("sys", "user", None)
        assert ei.value.retry_after == 2.0
    finally:
        await client.close()
```

- [ ] **Step 2: Run, expect fail** — `uv run python -m pytest tests/test_fallback.py -k "cerebras_404 or cerebras_429_is_throttle" -q`
Expected: FAIL (raises httpx error / wrong exception).

- [ ] **Step 3: Implement** the helper + small parsers + rewire `_call_cerebras`.

Add module-level helper:
```python
def _parse_retry_after(value: str | None) -> float | None:
    """Parse a Retry-After header expressed in seconds. Ignore HTTP-date form."""
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


_MODEL_GONE_MARKERS = ("model_not_found", "does not exist", "not exist", "no access", "not_found")
```

Add method:
```python
    async def _call_openai_compatible(
        self,
        *,
        provider: Provider,
        base_url: str,
        model: str,
        api_key: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict | None,
        extra_body: dict | None = None,
        throttle_delay: float = 0.0,
        empty_is_throttle: bool = False,
    ) -> dict:
        """Shared OpenAI-compatible chat-completions call (Cerebras/OpenRouter/Mistral).

        Maps 429→ProviderThrottledError, model 404/400→ProviderExhaustedError,
        5xx→retried then ProviderThrottledError. Optionally treats an empty
        completion as a throttle (OpenRouter silent-429 mode).
        """
        if not api_key:
            raise ProviderExhaustedError(f"{provider.value} api key not configured")

        body: dict = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
        }
        if json_schema:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "classification", "schema": json_schema, "strict": True},
            }
        else:
            body["response_format"] = {"type": "json_object"}
        if extra_body:
            body.update(extra_body)

        async def _do_call() -> dict:
            resp = await self._http.post(
                base_url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
            )
            if resp.status_code == 429:
                raise ProviderThrottledError(
                    f"{provider.value} 429", retry_after=_parse_retry_after(resp.headers.get("retry-after"))
                )
            if resp.status_code in (400, 404):
                low = resp.text.lower()
                if any(m in low for m in _MODEL_GONE_MARKERS):
                    raise ProviderExhaustedError(f"{provider.value} model unavailable: {resp.text[:160]}")
            resp.raise_for_status()
            self.quota.check_headers(provider, dict(resp.headers))
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            if empty_is_throttle and (content is None or not content.strip()):
                raise ProviderThrottledError(f"{provider.value} empty completion (possible 429)")
            return json.loads(content)

        try:
            result = await _retry_on_5xx(_do_call, label=provider.value)
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                raise ProviderThrottledError(f"{provider.value} {e.response.status_code}") from e
            raise
        if throttle_delay:
            await asyncio.sleep(throttle_delay)
        return result
```

Rewire `_call_cerebras` to delegate:
```python
    async def _call_cerebras(self, system_prompt, user_prompt, json_schema):
        return await self._call_openai_compatible(
            provider=Provider.CEREBRAS,
            base_url="https://api.cerebras.ai/v1/chat/completions",
            model=settings.cerebras_model,
            api_key=settings.cerebras_api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema=json_schema,
            throttle_delay=settings.cerebras_inter_call_delay,
        )
```

- [ ] **Step 4: Run, expect pass** — `uv run python -m pytest tests/test_fallback.py -q`
Expected: green. NOTE: the existing `test_call_cerebras_sleeps_after_success` mocks a 200 with `{"choices":[{"message":{"content":'{"signals": []}'}}]}` and asserts the throttle sleep fired — still valid via the helper. If it now also triggers `check_headers`, that's fine (no rate headers in the mock).

- [ ] **Step 5: Commit**
```bash
git add pipeline/classifier/llm.py tests/test_fallback.py
git commit -m "feat(llm): shared OpenAI-compat helper; Cerebras 404→exhaust, 429→throttle"
```

---

## Task 4: Gemini 429-body parsing

**Files:** Modify `pipeline/classifier/llm.py`; Test `tests/test_fallback.py`

- [ ] **Step 1: Write failing tests**
```python
@pytest.mark.asyncio
async def test_gemini_per_minute_429_is_throttle(monkeypatch):
    monkeypatch.setattr("pipeline.config.settings.gemini_api_key", "k", raising=False)
    from unittest.mock import AsyncMock
    client = LLMClient()
    body = {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
         "violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "21s"}]}}
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
    body = {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
         "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}
    client._http.post = AsyncMock(return_value=_http_response(429, json_body=body))
    try:
        with pytest.raises(ProviderExhaustedError):
            await client._call_gemini("sys", "user")
    finally:
        await client.close()
```

- [ ] **Step 2: Run, expect fail** — `uv run python -m pytest tests/test_fallback.py -k gemini_per -q`
Expected: FAIL (raises httpx 429 error, not the mapped exceptions).

- [ ] **Step 3: Implement** — add parsers + edit `_call_gemini`'s `_do_call`.
```python
def _parse_duration(s: str | None) -> float | None:
    """Parse a protobuf duration like '21s' → 21.0."""
    if not s:
        return None
    s = s.strip()
    try:
        return float(s[:-1]) if s.endswith("s") else float(s)
    except ValueError:
        return None


def _gemini_429_to_error(resp: httpx.Response) -> Exception:
    """Map a Gemini 429 to terminal (PerDay) or transient (PerMinute/unknown)."""
    try:
        details = resp.json().get("error", {}).get("details", [])
    except Exception:
        return ProviderThrottledError("gemini 429 (unparseable)")
    per_day = False
    retry_after = None
    for d in details:
        for v in d.get("violations", []):
            if "PerDay" in v.get("quotaId", ""):
                per_day = True
        if d.get("retryDelay"):
            retry_after = _parse_duration(d["retryDelay"])
    if per_day:
        return ProviderExhaustedError("gemini per-day quota exhausted")
    return ProviderThrottledError("gemini per-minute throttle", retry_after=retry_after)
```
In `_call_gemini`, replace the `_do_call` body's start:
```python
        async def _do_call() -> dict:
            resp = await self._http.post(...)  # unchanged args
            if resp.status_code == 429:
                raise _gemini_429_to_error(resp)
            resp.raise_for_status()
            data = resp.json()
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(content)

        try:
            return await _retry_on_5xx(_do_call, label="gemini")
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                raise ProviderThrottledError(f"gemini {e.response.status_code}") from e
            raise
```

- [ ] **Step 4: Run, expect pass** — `uv run python -m pytest tests/test_fallback.py -q`
- [ ] **Step 5: Commit**
```bash
git add pipeline/classifier/llm.py tests/test_fallback.py
git commit -m "feat(llm): parse Gemini 429 details[] — PerMinute→throttle, PerDay→exhaust"
```

---

## Task 5: Wire OpenRouter + Mistral providers

**Files:** Modify `pipeline/classifier/llm.py`; Test `tests/test_fallback.py`

- [ ] **Step 1: Write failing tests**
```python
@pytest.mark.asyncio
async def test_openrouter_empty_completion_is_throttle(monkeypatch):
    monkeypatch.setattr("pipeline.config.settings.openrouter_api_key", "k", raising=False)
    async def _no_sleep(_): return None
    monkeypatch.setattr("pipeline.classifier.llm.asyncio.sleep", _no_sleep)
    from unittest.mock import AsyncMock
    client = LLMClient()
    client._http.post = AsyncMock(return_value=_http_response(
        200, json_body={"choices": [{"message": {"content": ""}}]}))
    try:
        with pytest.raises(ProviderThrottledError):
            await client._call_openrouter("sys", "user", None)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_openrouter_happy_path(monkeypatch):
    monkeypatch.setattr("pipeline.config.settings.openrouter_api_key", "k", raising=False)
    async def _no_sleep(_): return None
    monkeypatch.setattr("pipeline.classifier.llm.asyncio.sleep", _no_sleep)
    from unittest.mock import AsyncMock
    client = LLMClient()
    client._http.post = AsyncMock(return_value=_http_response(
        200, json_body={"choices": [{"message": {"content": '{"signals": []}'}}]}))
    try:
        assert await client._call_openrouter("sys", "user", None) == {"signals": []}
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_mistral_happy_path(monkeypatch):
    monkeypatch.setattr("pipeline.config.settings.mistral_api_key", "k", raising=False)
    async def _no_sleep(_): return None
    monkeypatch.setattr("pipeline.classifier.llm.asyncio.sleep", _no_sleep)
    from unittest.mock import AsyncMock
    client = LLMClient()
    client._http.post = AsyncMock(return_value=_http_response(
        200, json_body={"choices": [{"message": {"content": '{"signals": []}'}}]}))
    try:
        assert await client._call_mistral("sys", "user", None) == {"signals": []}
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_pick_providers_full_order():
    client = LLMClient()
    try:
        assert client._pick_providers() == [
            Provider.GROQ, Provider.OPENROUTER, Provider.GEMINI, Provider.MISTRAL, Provider.CEREBRAS,
        ]
    finally:
        await client.close()
```

- [ ] **Step 2: Run, expect fail** — `uv run python -m pytest tests/test_fallback.py -k "openrouter or mistral or pick_providers_full" -q`
Expected: FAIL (stubs raise ProviderExhaustedError; order wrong).

- [ ] **Step 3: Implement** — replace the Task-2 stubs with real bodies; update `_pick_providers`.
```python
    async def _call_openrouter(self, system_prompt, user_prompt, json_schema):
        return await self._call_openai_compatible(
            provider=Provider.OPENROUTER,
            base_url="https://openrouter.ai/api/v1/chat/completions",
            model=settings.openrouter_model,
            api_key=settings.openrouter_api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema=json_schema,
            extra_body={"provider": {"require_parameters": True}} if json_schema else None,
            throttle_delay=settings.openrouter_inter_call_delay,
            empty_is_throttle=True,
        )

    async def _call_mistral(self, system_prompt, user_prompt, json_schema):
        return await self._call_openai_compatible(
            provider=Provider.MISTRAL,
            base_url="https://api.mistral.ai/v1/chat/completions",
            model=settings.mistral_model,
            api_key=settings.mistral_api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema=json_schema,
            throttle_delay=settings.mistral_inter_call_delay,
        )
```
Update `_pick_providers`:
```python
    def _pick_providers(self) -> list[Provider]:
        order = [
            Provider.GROQ, Provider.OPENROUTER, Provider.GEMINI, Provider.MISTRAL, Provider.CEREBRAS,
        ]
        return [p for p in order if not self.quota.is_exhausted(p)]
```

- [ ] **Step 4: Fix the stale exhausted-set test** — in `tests/test_fallback.py`, `test_fallback_groq_and_cerebras_exhausted` currently asserts `_pick_providers() == [Provider.GEMINI]`. Update:
```python
        client.quota.mark_exhausted(Provider.GROQ)
        client.quota.mark_exhausted(Provider.CEREBRAS)
        providers = client._pick_providers()
        assert providers == [Provider.OPENROUTER, Provider.GEMINI, Provider.MISTRAL]
```

- [ ] **Step 5: Run, expect pass** — `uv run python -m pytest tests/test_fallback.py -q`
- [ ] **Step 6: Commit**
```bash
git add pipeline/classifier/llm.py tests/test_fallback.py
git commit -m "feat(llm): wire OpenRouter (empty=throttle) + Mistral tiers; 5-tier order"
```

---

## Task 6: Per-batch isolation + alignment in main.py

**Files:** Modify `pipeline/main.py`; Test `tests/test_main_isolation.py` (new)

- [ ] **Step 1: Write failing test** (`tests/test_main_isolation.py`)
```python
"""One failed classify batch must not abort the run; alignment is preserved."""
import pytest
from pipeline.classifier.categorizer import Category, ClassifiedSignal
from pipeline.classifier.llm import LLMError
from pipeline.scraper.models import RawSignal


def _sig(i):
    return RawSignal(source=f"S{i}", url=f"https://e.test/{i}",
                     title=f"t{i}", content=f"content {i} " * 5)


def _classified(i):
    return ClassifiedSignal(category=Category.OTHER, relevance_score=3, summary=f"sum {i} ....")


@pytest.mark.asyncio
async def test_failed_batch_skipped_alignment_preserved(monkeypatch):
    from pipeline import main as m

    signals = [_sig(i) for i in range(6)]
    types = ["customer"] * 6

    async def fake_classify(client, batch_dicts, target_types=None):
        # Batch starting at index 2 (2nd batch, size 2) fails entirely.
        if batch_dicts[0]["source"] == "S2":
            raise LLMError("all providers down for this batch")
        return [_classified(d["source"]) for d in batch_dicts]

    monkeypatch.setattr(m, "classify_signals", fake_classify)

    processed, classified, out_types = await m._classify_in_batches(
        client=object(), signals=signals, types=types, batch_size=2
    )
    # Batch [S2,S3] dropped; 4 signals survive, perfectly aligned.
    assert [s.source for s in processed] == ["S0", "S1", "S4", "S5"]
    assert len(classified) == len(processed) == len(out_types) == 4
```

- [ ] **Step 2: Run, expect fail** — `uv run python -m pytest tests/test_main_isolation.py -q`
Expected: FAIL (`_classify_in_batches` missing).

- [ ] **Step 3: Implement** — add to `pipeline/main.py`. First add import: `from pipeline.classifier.llm import LLMClient, LLMError`. Add the function:
```python
async def _classify_in_batches(client, signals, types, batch_size):
    """Classify signals in batches; a batch whose providers all fail is skipped
    (logged), not fatal. Returns (processed_signals, classified, types) kept in
    lockstep so downstream zips stay aligned."""
    processed, all_classified, all_types = [], [], []
    for i in range(0, len(signals), batch_size):
        batch = signals[i : i + batch_size]
        batch_types = types[i : i + batch_size]
        try:
            classified = await classify_signals(
                client, [s.model_dump() for s in batch], target_types=batch_types
            )
        except LLMError as e:
            logger.error(f"Classify failed for batch @ {i} ({len(batch)} signals), skipping: {e}")
            continue
        n = len(classified)
        processed.extend(batch[:n])
        all_classified.extend(classified)
        all_types.extend(batch_types[:n])
    return processed, all_classified, all_types
```

- [ ] **Step 4: Run, expect pass** — `uv run python -m pytest tests/test_main_isolation.py -q`

- [ ] **Step 5: Rewire `run_daily`'s classify loop** (lines ~201-215) to use the helper, then swap `unique`→`processed` downstream.
```python
            # Classify in batches (per-batch failures are isolated, not fatal)
            all_types_full = [type_map.get(s.source, "customer") for s in unique]
            async with LLMClient() as client:
                processed, all_classified, all_types = await _classify_in_batches(
                    client, unique, all_types_full, settings.max_signals_per_batch
                )

            if not all_classified:
                logger.error("All classify batches failed — no signals classified")
                await db.finish_scrape_log(
                    log_id, status="error",
                    error_message="all classify batches failed",
                    targets_success=len(raw_signals),
                    duration_ms=int((time.monotonic() - start_time) * 1000),
                )
                return
```
Then in the downstream calls, replace `unique` with `processed`:
- `await link_entities(db._pool, all_classified)` — unchanged.
- `source_names = [s.source for s in processed]`
- `signal_keys = [s.content_hash for s in processed]`
- `inserted = await db.insert_signals_batch(processed, all_classified)`
- `brief = await generate_brief(processed, all_classified, target_types=all_types, contacts=signal_contacts)`

- [ ] **Step 6: Run full suite** — `uv run python -m pytest -q -m "not integration"`
Expected: green.

- [ ] **Step 7: Commit**
```bash
git add pipeline/main.py tests/test_main_isolation.py
git commit -m "feat(pipeline): isolate per-batch classify failures + preserve alignment"
```

---

## Task 7: Brief generator fallback chain

**Files:** Modify `pipeline/brief/generator.py`; Test `tests/test_brief.py`

- [ ] **Step 1: Write failing test** (append to `tests/test_brief.py`)
```python
@pytest.mark.asyncio
async def test_brief_falls_through_to_openrouter(monkeypatch):
    import pipeline.brief.generator as g
    monkeypatch.setattr("pipeline.config.settings.gemini_api_key", "k", raising=False)
    monkeypatch.setattr("pipeline.config.settings.openrouter_api_key", "k", raising=False)

    async def boom(_): raise RuntimeError("down")
    async def ok(_): return "BRIEF OK"
    monkeypatch.setattr(g, "_generate_with_gemini", boom)
    monkeypatch.setattr(g, "_generate_with_groq", boom)
    monkeypatch.setattr(g, "_generate_with_openrouter", ok)

    out = await g._generate_brief_text("prompt")
    assert out == "BRIEF OK"
```

- [ ] **Step 2: Run, expect fail** — `uv run python -m pytest tests/test_brief.py -k falls_through -q`
Expected: FAIL (`_generate_brief_text` / `_generate_with_openrouter` missing).

- [ ] **Step 3: Implement** — in `generator.py` extract the provider-selection tail of `generate_brief` into `_generate_brief_text`, add OpenRouter, and add 429-awareness to Gemini.

Replace the tail of `generate_brief` (the `if settings.gemini_api_key: ...` block) with:
```python
    return await _generate_brief_text(user_prompt)


async def _generate_brief_text(user_prompt: str) -> str | None:
    """Try the brief providers in order; first success wins."""
    chain: list[tuple[str, bool]] = [
        ("gemini", bool(settings.gemini_api_key)),
        ("groq", bool(settings.groq_api_key)),
        ("openrouter", bool(settings.openrouter_api_key)),
    ]
    fns = {
        "gemini": _generate_with_gemini,
        "groq": _generate_with_groq,
        "openrouter": _generate_with_openrouter,
    }
    last_exc: Exception | None = None
    for name, enabled in chain:
        if not enabled:
            continue
        try:
            return await fns[name](user_prompt)
        except Exception as e:  # noqa: BLE001 — try next provider
            last_exc = e
            logger.warning(f"Brief via {name} failed: {e}")
    logger.error(f"All brief providers failed: {last_exc}")
    return None
```
Add OpenRouter brief generator:
```python
async def _generate_with_openrouter(user_prompt: str) -> str:
    """Fallback brief via OpenRouter (OpenAI-compatible)."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}",
                     "Content-Type": "application/json"},
            json={
                "model": settings.openrouter_model,
                "messages": [
                    {"role": "system", "content": BRIEF_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
```
Add 429 backoff to `_generate_with_gemini` — inside its `except httpx.HTTPStatusError as e:` block, before the `if e.response.status_code < 500: raise`:
```python
                if e.response.status_code == 429:
                    # transient per-minute throttle → brief budget is 1 call, so
                    # back off once within attempts; per-day → just fall through.
                    last_exc = e
                    if attempt < BRIEF_RETRY_MAX_ATTEMPTS - 1:
                        await asyncio.sleep(BRIEF_RETRY_BASE_DELAY * (2**attempt))
                        continue
                    raise
```

- [ ] **Step 4: Run, expect pass** — `uv run python -m pytest tests/test_brief.py -q`
- [ ] **Step 5: Commit**
```bash
git add pipeline/brief/generator.py tests/test_brief.py
git commit -m "feat(brief): 3-tier fallback (Gemini→Groq→OpenRouter) + 429 backoff"
```

---

## Task 8: Probe scripts (live verification tooling)

**Files:** Create `scripts/probe_openrouter.py`, `scripts/probe_mistral.py`, `scripts/probe_gemini.py`

- [ ] **Step 1: Create `scripts/probe_gemini.py`** — capture a real 429 body + confirm classify(flash-lite)/brief(flash) both POST.
```python
"""Probe Gemini: POST flash-lite + flash, and dump any 429 body to confirm
details[].quotaId (PerMinute vs PerDay) and RetryInfo. Run:
    GEMINI_API_KEY=<key> uv run python scripts/probe_gemini.py
"""
from __future__ import annotations
import asyncio, os, sys
import httpx
from pipeline.config import settings

async def _try(client, key, model):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {"contents": [{"parts": [{"text": "ping"}]}],
               "generationConfig": {"responseMimeType": "application/json"}}
    r = await client.post(url, params={"key": key}, json=payload)
    print(f"  {model:<28} HTTP {r.status_code}")
    if r.status_code != 200:
        print("   body:", r.text[:600])

async def main() -> int:
    key = os.environ.get("GEMINI_API_KEY") or settings.gemini_api_key
    if not key:
        print("ERROR: GEMINI_API_KEY not set"); return 1
    async with httpx.AsyncClient(timeout=20.0) as client:
        print("=== single POST per model ===")
        await _try(client, key, settings.gemini_lite_model)
        await _try(client, key, settings.gemini_model)
        print("=== 20-call burst on flash-lite to trip per-minute 429 ===")
        for i in range(20):
            await _try(client, key, settings.gemini_lite_model)
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: Create `scripts/probe_openrouter.py`** — list key info + 25-call burst to observe whether 429 is an error or empty body.
```python
"""Probe OpenRouter: GET /key (quota), then a 25-call burst on the configured
free model to observe 429 behavior (error vs EMPTY completion). Run:
    OPENROUTER_API_KEY=<key> uv run python scripts/probe_openrouter.py
"""
from __future__ import annotations
import asyncio, os, sys
import httpx
from pipeline.config import settings

async def main() -> int:
    key = os.environ.get("OPENROUTER_API_KEY") or settings.openrouter_api_key
    if not key:
        print("ERROR: OPENROUTER_API_KEY not set"); return 1
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get("https://openrouter.ai/api/v1/key", headers=h)
        print("GET /key:", r.status_code, r.text[:400])
        body = {"model": settings.openrouter_model,
                "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}
        empties = errors = ok = 0
        for i in range(25):
            r = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=h, json=body)
            if r.status_code != 200:
                errors += 1; print(f"  [{i}] HTTP {r.status_code} {r.text[:120]}")
            else:
                c = r.json()["choices"][0]["message"].get("content")
                if not c or not c.strip(): empties += 1
                else: ok += 1
        print(f"ok={ok} empty={empties} errors={errors}")
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 3: Create `scripts/probe_mistral.py`** — confirm free tier active + real RPM + json_schema.
```python
"""Probe Mistral: list models + 6-call burst to observe 2-RPM 429 + Retry-After. Run:
    MISTRAL_API_KEY=<key> uv run python scripts/probe_mistral.py
"""
from __future__ import annotations
import asyncio, os, sys
import httpx
from pipeline.config import settings

async def main() -> int:
    key = os.environ.get("MISTRAL_API_KEY") or settings.mistral_api_key
    if not key:
        print("ERROR: MISTRAL_API_KEY not set"); return 1
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get("https://api.mistral.ai/v1/models", headers=h)
        print("GET /models:", r.status_code)
        body = {"model": settings.mistral_model,
                "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}
        for i in range(6):
            r = await client.post("https://api.mistral.ai/v1/chat/completions", headers=h, json=body)
            print(f"  [{i}] HTTP {r.status_code} retry-after={r.headers.get('retry-after')} {r.text[:100]}")
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 4: Lint + commit**
```bash
uv run ruff check --fix scripts/ && uv run ruff format scripts/
git add scripts/probe_openrouter.py scripts/probe_mistral.py scripts/probe_gemini.py
git commit -m "chore(scripts): live probes for OpenRouter, Mistral, Gemini 429 bodies"
```

---

## Task 9: CI env + docs reconciliation

**Files:** Modify `.github/workflows/daily_pipeline.yml`, `RUNBOOK.md`, `docs/changelog.md`, `CLAUDE.md`

- [ ] **Step 1: CI env** — in `daily_pipeline.yml`, under the `Run pipeline` step `env:`, add:
```yaml
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
          MISTRAL_API_KEY: ${{ secrets.MISTRAL_API_KEY }}
```

- [ ] **Step 2: RUNBOOK** — update the "LLM Provider Limits" table to 5 tiers (Groq, OpenRouter, Gemini, Mistral, Cerebras gpt-oss-120b @ 5 RPM/12s), the architecture diagram's `classifier/llm.py` line to the new chain, and add Common-Issues rows: "OpenRouter empty completion → treated as 429 (transient), automatic"; "Mistral slow (2 RPM) → expected, deep backstop"; "Gemini 429 → PerMinute auto-retried, PerDay switches". Update the rotate-secrets table with `OPENROUTER_API_KEY` (openrouter.ai → Keys) and `MISTRAL_API_KEY` (console.mistral.ai → API Keys).

- [ ] **Step 3: changelog** — append a dated entry summarizing: 429 transient-vs-terminal split, Gemini details[] parsing, Cerebras qwen→gpt-oss-120b, Mistral+OpenRouter tiers, per-batch isolation, brief 3-tier fallback, batch 10→15. Bump the header date range.

- [ ] **Step 4: CLAUDE.md** — update the Stack section: classify chain now `Groq → OpenRouter → Gemini → Mistral → Cerebras (gpt-oss-120b)`; note both new free tiers; mention per-batch isolation.

- [ ] **Step 5: Commit**
```bash
git add .github/workflows/daily_pipeline.yml RUNBOOK.md docs/changelog.md CLAUDE.md
git commit -m "docs(resilience): runbook/changelog/CLAUDE + CI env for new tiers"
```

---

## Task 10: Full verification gate

- [ ] **Step 1: Lint** — `uv run ruff check --fix && uv run ruff format`  → clean.
- [ ] **Step 2: Types** — `uv run ty check pipeline/` (best-effort; note any new errors).
- [ ] **Step 3: Tests** — `uv run python -m pytest -q -m "not integration"` → all green (54 prior + new).
- [ ] **Step 4: Adversarial review** — request a focused review of `llm.py` + `main.py` changes (correctness of throttle escalation, alignment edge, empty-completion path, no double-retry).
- [ ] **Step 5: (LATER, needs keys)** run the three probe scripts with real keys; capture a provider/model/limit table for 2026-06-01. Add OPENROUTER_API_KEY + MISTRAL_API_KEY to local `.env` and GH secrets.
- [ ] **Step 6: (LATER, needs keys)** `gh workflow run daily_pipeline.yml` → confirm green E2E (2nd run/day dedups → short brief; expected).

---

## Self-review against spec

- **§3.1 exceptions** → Task 2 ✓ · **§3.2 throttle-retry** → Task 2 ✓ · **§3.3 shared helper** → Task 3 ✓ · **§3.4 Gemini 429 parse** → Task 4 ✓ · **§3.5 Cerebras swap** → Task 1+3 ✓ · **§3.6 tier order + brief path** → Task 5 + Task 7 ✓ · **§3.7 per-batch isolation+alignment** → Task 6 ✓ · **§3.8 batch 15** → Task 1 ✓ · **§4 config** → Task 1 ✓ · **§5 tests (9)** → Tasks 2-7 ✓ · **§6 probes + manual** → Task 8 + Task 10 ✓ · **§7 files** → all covered.
- **Deviation from spec:** §4 listed `openrouter_models: list`; plan uses a single `openrouter_model: str` (model-rotation-on-429 deferred per spec §8 to avoid unused config). Spec §3.4 keeps `_retry_on_5xx` for 5xx; plan does too (5xx retried internally, then mapped to ProviderThrottledError so the throttle loop can still switch). Both intentional and consistent across tasks.
- **Placeholder scan:** none. **Type consistency:** `ProviderThrottledError(message, retry_after)`, `_call_with_throttle_retry`, `_call_openai_compatible`, `_classify_in_batches`, `_generate_brief_text`, `_generate_with_openrouter` used consistently across tasks.
