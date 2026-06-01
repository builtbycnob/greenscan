"""3-tier LLM client: Groq → Cerebras → Gemini with drain-and-switch quota management."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum

import httpx
from groq import AsyncGroq
from groq import RateLimitError as GroqRateLimitError

from pipeline.config import settings

logger = logging.getLogger(__name__)

RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY = 1.0


async def _retry_on_5xx(
    factory: Callable[[], Awaitable[dict]],
    label: str,
    max_attempts: int = RETRY_MAX_ATTEMPTS,
    base_delay: float = RETRY_BASE_DELAY,
) -> dict:
    """Retry an httpx-based async call on 5xx errors with exponential backoff.

    Does NOT catch 429 (caller maps it to ProviderExhaustedError) or 4xx.
    """
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await factory()
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500:
                raise
            last_exc = e
            logger.warning(
                f"{label} 5xx (attempt {attempt + 1}/{max_attempts}): {e.response.status_code}"
            )
        if attempt < max_attempts - 1:
            await asyncio.sleep(base_delay * (2**attempt))
    assert last_exc is not None
    raise last_exc


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a Retry-After header expressed in seconds. Ignore HTTP-date form."""
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


_MODEL_GONE_MARKERS = (
    "model_not_found",
    "does not exist",
    "not exist",
    "no access",
    "not_found",
)


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
    """Map a Gemini 429 to terminal (PerDay quota) or transient (PerMinute/unknown).

    Gemini emits no rate-limit headers, so the 429 body's error.details[] is the
    only signal: a violation whose quotaId contains 'PerDay' is terminal for the
    day; anything else (PerMinute/PerSecond/unknown) is a transient throttle.
    """
    try:
        details = resp.json().get("error", {}).get("details", [])
    except Exception:
        return ProviderThrottledError("gemini 429 (unparseable body)")
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


class Provider(StrEnum):
    GROQ = "groq"
    CEREBRAS = "cerebras"
    OPENROUTER = "openrouter"
    MISTRAL = "mistral"
    GEMINI = "gemini"


@dataclass
class QuotaState:
    """Track provider quota per pipeline run.

    Two-layer strategy:
    1. Proactive: switch at 90% usage (requests OR tokens) via response headers
    2. Reactive: on 429, mark exhausted immediately and move to next provider
    """

    exhausted: set[Provider] = field(default_factory=set)
    requests_used: dict[Provider, int] = field(
        default_factory=lambda: {
            Provider.GROQ: 0,
            Provider.CEREBRAS: 0,
            Provider.OPENROUTER: 0,
            Provider.MISTRAL: 0,
            Provider.GEMINI: 0,
        }
    )

    def mark_exhausted(self, provider: Provider) -> None:
        self.exhausted.add(provider)
        logger.info(f"{provider.value} exhausted for this run")

    def is_exhausted(self, provider: Provider) -> bool:
        return provider in self.exhausted

    def record_use(self, provider: Provider) -> None:
        self.requests_used[provider] += 1

    def check_headers(self, provider: Provider, headers: dict) -> None:
        """Check rate limit headers and mark exhausted at 90% usage.

        Checks both request and token limits — whichever hits 90% first
        triggers the switch to the next provider.
        """
        threshold = settings.quota_switch_pct
        for key in [
            "x-ratelimit-remaining-requests",
            "x-ratelimit-remaining-requests-day",
            "x-ratelimit-remaining-tokens",
            "x-ratelimit-remaining-tokens-day",
            # Cerebras emits per-minute token windows under this name.
            "x-ratelimit-remaining-tokens-minute",
        ]:
            remaining = headers.get(key)
            limit_key = key.replace("remaining", "limit")
            limit = headers.get(limit_key)
            if remaining is not None and limit is not None:
                remaining_val = int(remaining)
                limit_val = int(limit)
                if limit_val > 0:
                    used_pct = 1 - (remaining_val / limit_val)
                    if used_pct >= threshold:
                        kind = "tokens" if "token" in key else "requests"
                        logger.info(
                            f"{provider.value} at {used_pct:.0%} {kind} "
                            f"({remaining_val}/{limit_val} left), switching"
                        )
                        self.mark_exhausted(provider)
                        return


class LLMError(Exception):
    """All providers exhausted or unrecoverable error."""


class ProviderExhaustedError(Exception):
    """A provider is unusable for the rest of this run (per-day quota / model gone)."""


class ProviderThrottledError(Exception):
    """Transient throttle (per-minute 429 / empty completion / queue). Retry SAME provider."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LLMClient:
    """Multi-provider LLM client with fallback chain."""

    def __init__(self) -> None:
        self.quota = QuotaState()
        self._groq = AsyncGroq(api_key=settings.groq_api_key)
        self._http = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._groq.close()
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def classify(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict | None = None,
    ) -> dict:
        """Send a classification request through the fallback chain.

        Drain each provider fully before moving to the next. On a 429
        (rate limit), immediately mark the provider as exhausted for
        this run and try the next one.
        """
        providers = self._pick_providers()
        last_error = None

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
        caller switches to the next provider.
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
                delay = (
                    e.retry_after if e.retry_after is not None else RETRY_BASE_DELAY * (2**attempt)
                )
                logger.info(
                    f"{provider.value} throttled ({attempt + 1}/{attempts}), retry in {delay:.1f}s"
                )
                if attempt < attempts - 1:
                    await asyncio.sleep(delay)
        raise ProviderExhaustedError(f"{provider.value} throttled past retry budget: {last}")

    def _pick_providers(self) -> list[Provider]:
        """Return providers in priority order, skipping exhausted ones."""
        order = [
            Provider.GROQ,
            Provider.OPENROUTER,
            Provider.GEMINI,
            Provider.MISTRAL,
            Provider.CEREBRAS,
        ]
        return [p for p in order if not self.quota.is_exhausted(p)]

    async def _call_provider(
        self,
        provider: Provider,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict | None,
    ) -> dict:
        """Dispatch to one provider. Each provider maps its own errors to
        ProviderThrottledError (transient) or ProviderExhaustedError (terminal)."""
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

    async def _call_groq(
        self, system_prompt: str, user_prompt: str, json_schema: dict | None
    ) -> dict:
        # Groq llama-3.3-70b-versatile only supports json_object, not json_schema.
        # The schema is enforced via the system prompt + Pydantic post-validation.
        kwargs: dict = {
            "model": settings.groq_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        try:
            raw = await self._groq.chat.completions.with_raw_response.create(**kwargs)
        except GroqRateLimitError as e:
            raise ProviderThrottledError(f"groq rate limited: {e}") from e
        self.quota.check_headers(Provider.GROQ, dict(raw.headers))
        response = await raw.parse()
        content = response.choices[0].message.content
        return json.loads(content)

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

        Maps 429 → ProviderThrottledError, model 404/400 → ProviderExhaustedError,
        5xx → retried then ProviderThrottledError. Optionally treats an empty
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
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            if resp.status_code == 429:
                raise ProviderThrottledError(
                    f"{provider.value} 429",
                    retry_after=_parse_retry_after(resp.headers.get("retry-after")),
                )
            if resp.status_code in (400, 404):
                low = resp.text.lower()
                if any(m in low for m in _MODEL_GONE_MARKERS):
                    raise ProviderExhaustedError(
                        f"{provider.value} model unavailable: {resp.text[:160]}"
                    )
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

    async def _call_cerebras(
        self, system_prompt: str, user_prompt: str, json_schema: dict | None
    ) -> dict:
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

    async def _call_gemini(self, system_prompt: str, user_prompt: str) -> dict:
        if not settings.gemini_api_key:
            raise LLMError("Gemini API key not configured")

        payload = {
            "contents": [{"parts": [{"text": user_prompt}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1,
            },
        }

        async def _do_call() -> dict:
            resp = await self._http.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{settings.gemini_lite_model}:generateContent",
                params={"key": settings.gemini_api_key},
                headers={"Content-Type": "application/json"},
                json=payload,
            )
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
