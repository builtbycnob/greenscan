"""Probe Gemini: POST flash-lite + flash, and dump any 429 body to confirm
details[].quotaId (PerMinute vs PerDay) and RetryInfo.

Run:
    GEMINI_API_KEY=<key> uv run python scripts/probe_gemini.py
"""

from __future__ import annotations

import asyncio
import os
import sys

import httpx

from pipeline.config import settings


async def _try(client: httpx.AsyncClient, key: str, model: str) -> None:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": "ping"}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    r = await client.post(url, params={"key": key}, json=payload)
    print(f"  {model:<28} HTTP {r.status_code}")
    if r.status_code != 200:
        print("   body:", r.text[:600])


async def main() -> int:
    key = os.environ.get("GEMINI_API_KEY") or settings.gemini_api_key
    if not key:
        print("ERROR: GEMINI_API_KEY not set in env or .env")
        return 1
    async with httpx.AsyncClient(timeout=20.0) as client:
        print("=== single POST per model ===")
        await _try(client, key, settings.gemini_lite_model)
        await _try(client, key, settings.gemini_model)
        print("=== 20-call burst on flash-lite to trip a per-minute 429 ===")
        for _ in range(20):
            await _try(client, key, settings.gemini_lite_model)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
