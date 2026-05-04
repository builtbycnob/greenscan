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


class Provider(StrEnum):
    GROQ = "groq"
    CEREBRAS = "cerebras"
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
    """A single provider hit its rate limit (429)."""


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
                result = await self._call_provider(
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

    def _pick_providers(self) -> list[Provider]:
        """Return providers in priority order, skipping exhausted ones."""
        return [
            p
            for p in [Provider.GROQ, Provider.CEREBRAS, Provider.GEMINI]
            if not self.quota.is_exhausted(p)
        ]

    async def _call_provider(
        self,
        provider: Provider,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict | None,
    ) -> dict:
        """Call a single provider. Raises ProviderExhaustedError on 429."""
        try:
            if provider == Provider.GROQ:
                return await self._call_groq(system_prompt, user_prompt, json_schema)
            elif provider == Provider.CEREBRAS:
                return await self._call_cerebras(system_prompt, user_prompt, json_schema)
            else:
                return await self._call_gemini(system_prompt, user_prompt)
        except GroqRateLimitError as e:
            raise ProviderExhaustedError(f"Groq rate limited: {e}") from e
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise ProviderExhaustedError(f"{provider.value} rate limited (429)") from e
            raise

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

        raw = await self._groq.chat.completions.with_raw_response.create(**kwargs)
        self.quota.check_headers(Provider.GROQ, dict(raw.headers))
        response = await raw.parse()
        content = response.choices[0].message.content
        return json.loads(content)

    async def _call_cerebras(
        self, system_prompt: str, user_prompt: str, json_schema: dict | None
    ) -> dict:
        body: dict = {
            "model": settings.cerebras_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
        }
        if json_schema:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "classification",
                    "schema": json_schema,
                    "strict": True,
                },
            }
        else:
            body["response_format"] = {"type": "json_object"}

        async def _do_call() -> dict:
            resp = await self._http.post(
                "https://api.cerebras.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.cerebras_api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            self.quota.check_headers(Provider.CEREBRAS, dict(resp.headers))
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)

        result = await _retry_on_5xx(_do_call, label="cerebras")
        # Throttle to stay under Cerebras free-tier RPM cap (≈30 RPM).
        await asyncio.sleep(settings.cerebras_inter_call_delay)
        return result

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
            resp.raise_for_status()
            data = resp.json()
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(content)

        return await _retry_on_5xx(_do_call, label="gemini")
