"""Probe Mistral: list models + a 6-call burst to observe the 2-RPM 429 + Retry-After.

Run:
    MISTRAL_API_KEY=<key> uv run python scripts/probe_mistral.py
"""

from __future__ import annotations

import asyncio
import os
import sys

import httpx

from pipeline.config import settings


async def main() -> int:
    key = os.environ.get("MISTRAL_API_KEY") or settings.mistral_api_key
    if not key:
        print("ERROR: MISTRAL_API_KEY not set in env or .env")
        return 1
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get("https://api.mistral.ai/v1/models", headers=headers)
        print("GET /models:", r.status_code)

        body = {
            "model": settings.mistral_model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }
        for i in range(6):
            r = await client.post(
                "https://api.mistral.ai/v1/chat/completions", headers=headers, json=body
            )
            print(
                f"  [{i}] HTTP {r.status_code} "
                f"retry-after={r.headers.get('retry-after')} {r.text[:100]}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
