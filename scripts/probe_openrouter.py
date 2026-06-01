"""Probe OpenRouter: GET /key (quota), then a 25-call burst on the configured
free model to observe 429 behavior (proper error vs EMPTY completion).

Run:
    OPENROUTER_API_KEY=<key> uv run python scripts/probe_openrouter.py
"""

from __future__ import annotations

import asyncio
import os
import sys

import httpx

from pipeline.config import settings


async def main() -> int:
    key = os.environ.get("OPENROUTER_API_KEY") or settings.openrouter_api_key
    if not key:
        print("ERROR: OPENROUTER_API_KEY not set in env or .env")
        return 1
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get("https://openrouter.ai/api/v1/key", headers=headers)
        print("GET /key:", r.status_code, r.text[:400])

        body = {
            "model": settings.openrouter_model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }
        empties = errors = ok = 0
        for i in range(25):
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body
            )
            if r.status_code != 200:
                errors += 1
                print(f"  [{i}] HTTP {r.status_code} {r.text[:120]}")
            else:
                content = r.json()["choices"][0]["message"].get("content")
                if not content or not content.strip():
                    empties += 1
                else:
                    ok += 1
        print(f"ok={ok} empty={empties} errors={errors}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
