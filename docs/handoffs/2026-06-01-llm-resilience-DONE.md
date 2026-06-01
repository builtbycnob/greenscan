# Handoff — LLM tier resilience — COMPLETE (code), keys pending — 2026-06-01

## §0 State
- Branch: `feat/llm-tier-resilience` @ `a1abdae` (14 commits off `main`@`7ec5489`) — **NOT pushed, NOT merged**
- Tests: **79 passed, 11 deselected** — `uv run python -m pytest -q -m "not integration"`
- Lint: `uv run ruff check` clean. Types: `ty` not installed in this env (skipped).
- Process: brainstorm → spec (`docs/superpowers/specs/2026-06-01-llm-tier-resilience-design.md`) → plan (`docs/superpowers/plans/…`) → TDD → **2 adversarial review rounds** (round 1 found 5 real bugs incl. a CRITICAL salvage misalignment → all fixed w/ regression tests; round 2 → 0 must-fix + 1 consistency polish applied).

## §1 What shipped
- **5-tier classify chain:** Groq → OpenRouter → Gemini(flash-lite) → Mistral → Cerebras(`gpt-oss-120b`). Brief: Gemini-flash → Groq → OpenRouter.
- **Transient vs terminal split** (`ProviderThrottledError` retry-same-tier ×4 honoring Retry-After/retryDelay → then switch; `ProviderExhaustedError` switch immediately). Gemini 429 body-parsed (`details[].quotaId` PerMinute/PerDay — Gemini has no rate headers). Any 4xx / malformed / non-JSON 200 → exhaust. Empty completion → throttle. Cerebras 404 → exhaust-for-run.
- **Per-batch isolation + alignment** (`main.py:_classify_in_batches` + position-preserving `classify_signals` returning a None-aligned list).
- Config: `cerebras_model=gpt-oss-120b` (12s/5RPM), OpenRouter+Mistral keys/models/delays, `max_signals_per_batch=15`, `throttle_retry_max_attempts=4`.
- Docs reconciled (RUNBOOK 5-tier table, CLAUDE.md, changelog #35), CI env (`OPENROUTER_API_KEY`+`MISTRAL_API_KEY`), 3 probe scripts.

## §2 ⭐ Remaining — needs founder action (the ONLY blockers)
1. Create free **Mistral** key (console.mistral.ai, no card, phone verify) + **OpenRouter** key (openrouter.ai; fund **$10 once** for the 1000-RPD tier).
2. Add `MISTRAL_API_KEY` + `OPENROUTER_API_KEY` to local `.env` AND GitHub repo secrets.
3. Live verify: `uv run python scripts/probe_openrouter.py`, `… probe_mistral.py`, `… probe_gemini.py` → confirm 200s + capture a {provider, model, limit} table. **Watch for:** OpenRouter 429-as-empty-body; Mistral real RPM (2 vs reported 5) + whether `mistral-small-latest` honors strict `json_schema` (if it 400s on schema, send `json_object` for it); Gemini real 429 body shape.
4. `gh workflow run daily_pipeline.yml` → green E2E (2nd run/day dedups → short brief; expected).
5. Merge `feat/llm-tier-resilience` → `main`, push.

## §3 Notes / risks
- Every free tier here is mutable (Cerebras just proved it) — durable insurance is the 5-tier depth, not any one provider. Numeric RPM/RPD caps are medium-confidence → rely on 429-parsing + client throttle, already implemented.
- Accepted tradeoffs (not bugs): transient 4xx (408/409/425) exhaust-for-run; a generic unhandled exception exhausts the tier for the run — both conservative given 5-tier depth + reliability≫speed.
- `git diff main...HEAD` = 17 files, +~2400/−100.
