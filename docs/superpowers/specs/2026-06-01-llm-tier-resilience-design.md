# Design — LLM tier resilience

- **Date:** 2026-06-01
- **Branch target:** feature branch off `main` @ `7ec5489`
- **Mandate (§0):** No single LLM tier vanishing may abort the daily pipeline. Reliability >> speed (founder reads the brief async; +1-2 min runtime is fine). Budget €0/month (one-time $10 OpenRouter unlock approved as a non-recurring exception).

---

## 1. Problem & verified root cause

The 3-tier fallback (`Groq → Cerebras → Gemini`) has collapsed to ~1.x working tiers; ~24% of scheduled runs fail (May 23/24/29/30/31). Two **independent** failure layers:

### Layer 1 — provider chain (`pipeline/classifier/llm.py`)
- **Cerebras dead:** configured `qwen-3-235b-a22b-instruct-2507` returns **404 model_not_found** — live-confirmed 2026-06-01 and corroborated by Cerebras docs (qwen delisted from free roster, now Dedicated/paid only). The 404 is **not** marked exhausted, so it wastes ~8 round-trips/run (one per batch).
- **Gemini load-bearing + fragile:** a single *transient per-minute* 429 is mapped to `ProviderExhaustedError` → marked **permanently** exhausted → no tiers left → `LLMError` → run aborts. A ~60s backoff would have succeeded. Gemini also emits **no `x-ratelimit-*` headers**, so the proactive `QuotaState.check_headers()` 90%-switch is a **silent no-op** for it — all Gemini resilience must come from parsing the 429 body.
- **503 outlasting 3 quick retries** (May 23/24) → same abort.

### Layer 2 — orchestration (`pipeline/main.py:201-215`)
The classify loop has **no per-batch error handling**, and nothing is persisted until **after** the full loop (`insert_signals_batch` at line 233). So one fatal `LLMError` on batch 9 of 20 discards **all** prior batches' work and aborts the run. This is the true "single tier → dead pipeline" mechanism, independent of provider health.

---

## 2. Provider reality table (verified 2026-06-01)

| Provider | Model | Status today | Binding free limit | OpenAI-compat | JSON | Notes |
|---|---|---|---|---|---|---|
| Groq | `llama-3.3-70b-versatile` | ✅ 200 | 1000 RPD / 100K TPD / **12K TPM** | yes | json_object | Primary anchor, most stable; drains on TPM in 2-3 batches; proactive headers work |
| Cerebras | `gpt-oss-120b` | ✅ 200 (live probe) | **5 RPM** / 1M TPD / 30K TPM | yes | json_object | `qwen-3-235b` = 404 (drop it). `zai-glm-4.7` also 200. `queue_exceeded` 429s are transient (remaining-tokens-minute stays healthy) |
| OpenRouter | `meta-llama/llama-3.3-70b-instruct:free` (+ rotate `qwen/qwen3-coder:free`) | n/a (new) | **1000 RPD** (after one-time $10) / 20 RPM | yes | json_object + json_schema strict | Many interchangeable :free models behind one endpoint. **Gotcha: 429 can return an EMPTY completion, not an error** → must detect. Use `extra_body {"provider":{"require_parameters":true}}`. Poll `GET /api/v1/key`. |
| Mistral | `mistral-small-latest` | n/a (new) | 1B tokens/MONTH / **2 RPM** | yes | json_object + json_schema | Truly free, no card (phone verify). Stable EU roster (no week-to-week flapping). Must self-throttle to ≤2 RPM (~30s spacing), honor `Retry-After`. |
| Gemini | `gemini-2.5-flash-lite` (classify) / `gemini-2.5-flash` (brief) | ✅ (prod) | ~1000 RPD flash-lite / ~250 RPD flash (separate per-model buckets); ~10-15 RPM | partial (native) | responseMimeType json | **No rate-limit headers.** 429 body carries `error.details[]` → parse `quotaId`: `...PerMinute...`→transient, `...PerDay...`→terminal. Numeric caps MEDIUM-confidence; verify live. |

*Confidence flags:* Cerebras 5 RPM and Gemini 429-body structure are HIGH confidence (official docs + real payloads). Exact Gemini/Groq/Mistral numeric RPM/RPD are MEDIUM — Google/Groq no longer table free numbers. Design therefore relies on **429-body parsing + client-side throttling**, not hardcoded numeric caps.

---

## 3. Target architecture

### 3.1 Exception taxonomy (`llm.py`)
Replace the single binary signal with two:

- **`ProviderThrottledError(retry_after: float | None)`** — *transient*: per-minute 429, 503, OpenRouter empty-completion, Cerebras `queue_exceeded`. → **back off and retry the SAME provider**.
- **`ProviderExhaustedError`** — *permanent for this run*: per-day quota 429, `404/400 model_not_found`/unavailable. → **mark exhausted, switch immediately**.
- **`LLMError`** — all providers down for this call (unchanged; now caught per-batch in `main.py`).

### 3.2 Bounded throttle-retry before switching (`classify()`)
New private `_call_with_throttle_retry(provider, …)`:
```
for attempt in range(THROTTLE_RETRY_MAX_ATTEMPTS):   # = 4
    try: return await _call_provider(provider, …)
    except ProviderThrottledError as e:
        sleep(e.retry_after or exp_backoff(attempt))   # honor Retry-After / retryDelay
# budget spent → escalate to exhaustion so the outer loop switches
raise ProviderExhaustedError(f"{provider} throttled past retry budget")
```
The outer `classify()` loop: `ProviderExhaustedError` → `mark_exhausted` + continue; success → `record_use` + return. Because `QuotaState` persists across batches, a tier that truly exhausts is skipped by all later batches (bounded waste = one batch's retries).

### 3.3 Shared OpenAI-compatible call helper
Cerebras, OpenRouter, Mistral are all OpenAI-compatible → extract one helper (the pattern has clearly emerged; Groq stays on its SDK to preserve working header-based proactive switching):
```
async def _call_openai_compatible(self, *, provider, base_url, model, api_key,
        system_prompt, user_prompt, json_schema, extra_body=None,
        throttle_delay=0.0, empty_is_throttle=False) -> dict
```
Responsibilities: POST chat/completions; `check_headers`; map `429`→`ProviderThrottledError(Retry-After)`; map `404/400 model_not_found`→`ProviderExhaustedError`; 5xx→`_retry_on_5xx` then `ProviderThrottledError`; if `empty_is_throttle` and content is blank → `ProviderThrottledError` (OpenRouter); parse JSON; `sleep(throttle_delay)` after success (RPM throttle). `_call_cerebras/_call_openrouter/_call_mistral` become thin wrappers.

### 3.4 Gemini 429-body parsing (`_call_gemini`)
On `429`: parse `error.details[]`. If any violation `quotaId` contains `PerDay` → `ProviderExhaustedError`. Else (`PerMinute`/unknown) → `ProviderThrottledError(retry_after = RetryInfo.retryDelay)`. Keep `_retry_on_5xx` for 5xx.

### 3.5 Cerebras model swap
`cerebras_model`: `qwen-3-235b-a22b-instruct-2507` → `gpt-oss-120b`. Bump `cerebras_inter_call_delay` 6.0 → 12.0 (5 RPM = 1 call / 12s; old 6s ≈ 10 RPM exceeded the cap). Update the config comment block to reflect the 2026-06-01 reality.

### 3.6 Proposed tier order (tunable)
**Classify path:** `Groq → OpenRouter → Gemini(flash-lite) → Mistral → Cerebras(gpt-oss-120b)`
- Groq anchor; OpenRouter 1000-RPD headroom next; Gemini (now hardened) mid; Mistral rock-stable deep backstop; Cerebras (fast but queue-flaky, 5 RPM) last.

**Brief path** (`generator.py`, 1 call/run): `Gemini(flash) → Groq → OpenRouter(llama-3.3-70b:free)`. Add the same bounded 429-retry to the brief's Gemini call, and extend its fallback beyond Groq (today Groq is usually drained by classify time → silent no-brief gap).

### 3.7 Per-batch isolation + alignment fix (`main.py`)
Wrap each batch's `classify_signals` in `try/except LLMError` → log + skip batch, continue. **Alignment fix:** today downstream zips `unique` with the (possibly shorter) `all_classified`; skipping a batch worsens this. Track successfully-classified signals explicitly:
```
processed_signals, all_classified, all_types = [], [], []
for i in range(0, len(unique), batch_size):
    batch = unique[i:i+batch_size]; batch_types = [...]
    try: classified = await classify_signals(client, [s.model_dump() for s in batch], batch_types)
    except LLMError as e: logger.error(f"batch @ {i} failed, skipping {len(batch)}: {e}"); continue
    n = len(classified)
    processed_signals.extend(batch[:n]); all_classified.extend(classified); all_types.extend(batch_types[:n])
```
Then downstream uses `processed_signals` (not `unique`) for `link_entities` / `discover_contacts` (source_names, signal_keys) / `insert_signals_batch` / `generate_brief`. *(Known pre-existing edge: salvage path can drop a middle item, so `batch[:n]` may misalign by one in that rare case — preserved as-is, not expanded here.)*

### 3.8 Batch size
`max_signals_per_batch` 10 → 15. All chosen tiers have large context (≥128K) and no 8K-input cap (GitHub Models, which has one, is intentionally NOT wired). The categorizer salvage path already handles partial-batch parse failures.

---

## 4. Config changes (`config.py`)
```
cerebras_model: str = "gpt-oss-120b"          # was qwen-3-235b-a22b-instruct-2507 (404)
cerebras_inter_call_delay: float = 12.0       # was 6.0 — honor 5 RPM free cap
openrouter_api_key: str = ""
openrouter_models: list[str] = ["meta-llama/llama-3.3-70b-instruct:free", "qwen/qwen3-coder:free"]
openrouter_inter_call_delay: float = 3.0      # ≤20 RPM
mistral_api_key: str = ""
mistral_model: str = "mistral-small-latest"
mistral_inter_call_delay: float = 31.0        # ≤2 RPM
max_signals_per_batch: int = 15               # was 10
# retry tuning
throttle_retry_max_attempts: int = 4
```
GitHub Actions: add `OPENROUTER_API_KEY` + `MISTRAL_API_KEY` to workflow env + repo secrets. Local `.env`: add both keys.

---

## 5. Testing (`tests/test_fallback.py` — all mocked, no real API)
1. transient per-minute Gemini 429 (parsed) → retried → succeeds; provider **not** exhausted.
2. per-day Gemini 429 (parsed) → exhausted immediately, switches; no wasted retries.
3. Cerebras `404 model_not_found` → exhausted in **one** round-trip (not 8).
4. persistent 503 → retried then escalates to switch.
5. OpenRouter empty-completion → treated as throttle → retried.
6. only **one** reachable tier → throttle-retry exhausts budget → still returns a result when the tier finally answers.
7. throttle-retry budget spent on all tiers → `LLMError` (asserts the bound).
8. **per-batch isolation** (in a `main.py`-level test or a focused unit): one batch raises `LLMError` → loop continues, `processed_signals`/`all_classified` stay aligned, brief still generated from the rest.
9. new `_call_openrouter` / `_call_mistral` happy-path (mocked `client._http.post`).

Existing 54 tests must stay green (note: `test_fallback_groq_and_cerebras_exhausted` asserts `_pick_providers() == [Provider.GEMINI]` — update to the new tier set).

---

## 6. Manual verification (post-implementation, needs keys)
- Add `scripts/probe_openrouter.py` + `scripts/probe_mistral.py` (mirror `probe_cerebras.py`): list models + 25-call burst to observe 429 behavior (OpenRouter empty-body? Mistral Retry-After?).
- Add `scripts/probe_gemini.py`: capture a real 429 body, confirm `details[].quotaId` PerMinute/PerDay + whether flash/flash-lite are separate daily buckets.
- `uv run ruff check --fix && uv run ruff format` clean; `uv run python -m pytest -q -m "not integration"` green.
- `gh workflow run daily_pipeline.yml` → green E2E (2nd run/day dedups → short brief; expected).

## 7. Files touched
`pipeline/classifier/llm.py` (core), `pipeline/config.py`, `pipeline/main.py` (isolation+alignment), `pipeline/brief/generator.py` (brief hardening), `tests/test_fallback.py` (+ maybe `tests/test_main_isolation.py`), `.github/workflows/daily_pipeline.yml`, `RUNBOOK.md`, `docs/changelog.md`, `CLAUDE.md` (stack section), 3 new probe scripts, `.env` (local, untracked).

## 8. Out of scope
Frontend/dashboard, SERP monitoring, Telegram bot commands, schema/migrations, the Neon DB-drop fix (`aae17f1`), `.pptx`/presentation files. 2nd Gemini key (superseded by adding two real providers). GitHub Models / SambaNova / Together (rejected by research). OpenRouter model-rotation-on-429 beyond a 2-model list. Fixing the salvage middle-drop alignment edge (separate latent bug).

## 9. Risks
- Every free tier here is mutable (OpenRouter roster, Cerebras delisting just happened) — durable insurance is **chain depth (5 tiers)**, not any one provider.
- Numeric RPM/RPD are MEDIUM-confidence → rely on 429-parsing + client throttle, not hardcoded caps.
- Mistral 2 RPM means if it ever carries a full run it adds minutes — acceptable per reliability>>speed, and it's the deepest backstop.
- OpenRouter empty-completion-as-429 must be handled or it silently corrupts fallback — covered by test #5.
