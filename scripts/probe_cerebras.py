"""Probe Cerebras API: list models + test chat completion.

Run from project root with the same key the pipeline uses:

    uv run python scripts/probe_cerebras.py

If CEREBRAS_API_KEY is not in your local .env, you can pass it inline:

    CEREBRAS_API_KEY=<paste-key> uv run python scripts/probe_cerebras.py

The script does three things, each independently informative:
  1. GET /v1/models — reveals which models THIS api key can see
  2. POST /v1/chat/completions with the model the pipeline uses now
  3. POST /v1/chat/completions with each model GET returned (1 token)
"""

from __future__ import annotations

import asyncio
import os
import sys

import httpx

from pipeline.config import settings

CONFIGURED_MODEL = settings.cerebras_model


async def main() -> int:
    api_key = os.environ.get("CEREBRAS_API_KEY") or settings.cerebras_api_key
    if not api_key:
        print("ERROR: CEREBRAS_API_KEY not set in env or .env")
        return 1

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1) List models
        print("=== 1) GET /v1/models ===")
        try:
            r = await client.get("https://api.cerebras.ai/v1/models", headers=headers)
            print(f"HTTP {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                models = data.get("data", data)
                names = [m.get("id") if isinstance(m, dict) else str(m) for m in models]
                for n in names:
                    print(f"  - {n}")
            else:
                print(r.text[:500])
                names = []
        except Exception as e:
            print(f"  ERROR: {e}")
            names = []

        # 2) Test the model the pipeline is configured for
        print(f"\n=== 2) POST chat completion with '{CONFIGURED_MODEL}' (pipeline config) ===")
        ok = await _try_chat(client, headers, CONFIGURED_MODEL)
        if ok:
            print("  ✓ pipeline-configured model WORKS")

        # 3) Test each listed model with a minimal request
        if names:
            print("\n=== 3) POST chat completion with each listed model ===")
            for n in names:
                await _try_chat(client, headers, n)

    return 0


async def _try_chat(client: httpx.AsyncClient, headers: dict, model: str) -> bool:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    try:
        r = await client.post(
            "https://api.cerebras.ai/v1/chat/completions", headers=headers, json=body
        )
        if r.status_code == 200:
            print(f"  {model:<40} HTTP 200 OK")
            return True
        else:
            body_short = r.text[:200].replace("\n", " ")
            print(f"  {model:<40} HTTP {r.status_code}  {body_short}")
            return False
    except Exception as e:
        print(f"  {model:<40} ERROR: {e}")
        return False


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
