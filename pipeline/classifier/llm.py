"""3-tier LLM client: Groq → Cerebras → Gemini with retry and circuit breaker."""

import json
import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum

import httpx
from groq import AsyncGroq
from groq import RateLimitError as GroqRateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from pipeline.config import settings

logger = logging.getLogger(__name__)


class Provider(StrEnum):
    GROQ = "groq"
    CEREBRAS = "cerebras"
    GEMINI = "gemini"


@dataclass
class QuotaState:
    """Track remaining quota per provider (reset each pipeline run)."""

    remaining_requests: dict[Provider, int] = field(
        default_factory=lambda: {
            Provider.GROQ: 1000,
            Provider.CEREBRAS: 14400,
            Provider.GEMINI: 250,
        }
    )
    total_requests: dict[Provider, int] = field(
        default_factory=lambda: {
            Provider.GROQ: 1000,
            Provider.CEREBRAS: 14400,
            Provider.GEMINI: 250,
        }
    )
    requests_used: dict[Provider, int] = field(
        default_factory=lambda: {
            Provider.GROQ: 0,
            Provider.CEREBRAS: 0,
            Provider.GEMINI: 0,
        }
    )

    def update_from_headers(self, provider: Provider, headers: dict) -> None:
        remaining = headers.get("x-ratelimit-remaining-requests")
        if remaining is None:
            remaining = headers.get("x-ratelimit-remaining-requests-day")
        if remaining is not None:
            self.remaining_requests[provider] = int(remaining)

    def record_use(self, provider: Provider) -> None:
        self.requests_used[provider] += 1

    def should_switch(self, provider: Provider) -> bool:
        total = self.total_requests[provider]
        remaining = self.remaining_requests[provider]
        used_pct = 1 - (remaining / total) if total > 0 else 1
        return used_pct >= settings.groq_quota_switch_pct


class SimpleCircuitBreaker:
    """Minimal circuit breaker: opens after fail_max failures, resets after timeout."""

    def __init__(self, fail_max: int = 5, reset_timeout: float = 30.0) -> None:
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self.fail_count = 0
        self.opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.monotonic() - self.opened_at >= self.reset_timeout:
            self.opened_at = None
            self.fail_count = 0
            return False
        return True

    def record_success(self) -> None:
        self.fail_count = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.fail_count += 1
        if self.fail_count >= self.fail_max:
            self.opened_at = time.monotonic()


class CircuitBreakerError(Exception):
    pass


BREAKERS = {
    Provider.GROQ: SimpleCircuitBreaker(fail_max=5, reset_timeout=30),
    Provider.CEREBRAS: SimpleCircuitBreaker(fail_max=5, reset_timeout=30),
    Provider.GEMINI: SimpleCircuitBreaker(fail_max=5, reset_timeout=30),
}


class LLMError(Exception):
    """All providers exhausted or unrecoverable error."""


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
        """Send a classification request through the fallback chain."""
        providers = self._pick_providers()
        last_error = None

        for provider in providers:
            breaker = BREAKERS[provider]
            if breaker.is_open:
                logger.warning(f"{provider.value} circuit open, skipping")
                continue
            try:
                result = await self._call_provider(
                    provider, system_prompt, user_prompt, json_schema
                )
                breaker.record_success()
                self.quota.record_use(provider)
                return result
            except Exception as e:
                breaker.record_failure()
                last_error = e
                logger.warning(f"{provider.value} failed: {e}")
                continue

        raise LLMError(f"All providers exhausted. Last error: {last_error}")

    def _pick_providers(self) -> list[Provider]:
        """Order providers by preference, skipping exhausted ones."""
        order = []
        if not self.quota.should_switch(Provider.GROQ):
            order.append(Provider.GROQ)
        if not self.quota.should_switch(Provider.CEREBRAS):
            order.append(Provider.CEREBRAS)
        order.append(Provider.GEMINI)
        # Always include all as fallback even if quota is high
        for p in [Provider.GROQ, Provider.CEREBRAS, Provider.GEMINI]:
            if p not in order:
                order.append(p)
        return order

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, GroqRateLimitError)),
        wait=wait_exponential_jitter(initial=1, max=30, jitter=2),
        stop=stop_after_attempt(settings.max_retries_per_provider),
        reraise=True,
    )
    async def _call_provider(
        self,
        provider: Provider,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict | None,
    ) -> dict:
        if provider == Provider.GROQ:
            return await self._call_groq(system_prompt, user_prompt, json_schema)
        elif provider == Provider.CEREBRAS:
            return await self._call_cerebras(system_prompt, user_prompt, json_schema)
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

        raw = await self._groq.chat.completions.with_raw_response.create(**kwargs)
        self.quota.update_from_headers(Provider.GROQ, dict(raw.headers))
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

        resp = await self._http.post(
            "https://api.cerebras.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.cerebras_api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        resp.raise_for_status()
        self.quota.update_from_headers(Provider.CEREBRAS, dict(resp.headers))
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)

    async def _call_gemini(self, system_prompt: str, user_prompt: str) -> dict:
        if not settings.gemini_api_key:
            raise LLMError("Gemini API key not configured")

        resp = await self._http.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.gemini_lite_model}:generateContent",
            params={"key": settings.gemini_api_key},
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": user_prompt}]}],
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": 0.1,
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(content)
