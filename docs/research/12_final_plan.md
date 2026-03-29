# GreenScan — Final Implementation Plan

**Version:** 2.0
**Date:** 2026-03-29
**Status:** Ready for Day 0 execution
**Inputs:** Synthesis (09), Technical Review (10), Red Team Review (11), Original Specs (01-04)

---

## 1. Executive Summary

GreenScan is a market intelligence pipeline for Green Growth Innovations (greengrowth.tech),
a precision agriculture startup building universal retrofit yield monitors for combine and
potato harvesters. GreenScan monitors Green Growth's **target customers** (large US farm
operators, food processors, farmland investors, agri input companies) to detect sales
opportunities and market signals. Budget: EUR 0/month. ESADE I2P project.

### What We Are Building (3-Week MVP)

A Python pipeline running on GitHub Actions cron that scrapes target company websites and RSS
feeds, classifies signals using a 3-tier LLM fallback chain (Groq -> Cerebras -> Gemini),
stores results in Neon Postgres, generates a daily Battlefield Brief, and delivers it via
Telegram.

**No frontend. No email.** Telegram is the only delivery channel (founder-approved).

### What Changed from Original Specs

| Change | Why |
|---|---|
| Monitoring approach: target customers, not competitors | Green Growth needs sales leads, not competitive defense. 21 US companies in ICP list. |
| Classification: opportunity-focused categories | precision_ag_adoption, sustainability, vendor_search replace generic categories. |
| Frontend eliminated (was Next.js 14 on Vercel) | Over-engineered for 1-3 users. Vercel Hobby usable (not commercial) but unnecessary. |
| Email delivery removed | Founder explicitly approved Telegram-only in overview. |
| Cerebras added as first LLM fallback | Same model (Llama 3.3 70B), 10x Groq's TPM. No credit card required. |
| Groq RPD treated as UNVERIFIED (see Section 6) | Specs say 1,000; research found ~14,400. Plan works for both. |
| Team reduced from 4 devs to 1 dev + AI | Scope cut accordingly. 15 target companies in MVP (not 30). |
| Pipeline uses asyncio.Queue with backpressure | Decouples fast scraping from slow LLM classification. |
| NL-to-SQL moved to Phase 2 | Week 3 was overloaded. Pipeline + delivery is the MVP. |
| Brief generation uses Gemini 2.5 Flash (not Groq) | 1M context window. Better narrative quality. |
| All CI YAML uses `uv` (not `pip`) | Per CLAUDE.md mandate. |

### Key Numbers

| Metric | Value | Confidence |
|---|---|---|
| Daily LLM requests needed | ~200 RPD | High |
| Groq RPD limit | **1,000 RPD** (VERIFIED 2026-03-29) | High |
| Groq TPM limit | **12,000 TPM** (VERIFIED — better than 6K estimate) | High |
| Cerebras RPD limit | **14,400 RPD** (VERIFIED 2026-03-29) | High |
| Cerebras model | **Qwen 3 235B** (Llama 3.3 70B removed) | High |
| Neon Year 1 storage | ~30 MB (6% of 500 MB limit) | High |
| GH Actions monthly minutes | ~1,100-1,500 min (55-75% of 2,000) | Medium |
| Target companies in MVP | 15 of 21 (HIGH + some MEDIUM priority) | Decision based on red team feedback |
| Pipeline runtime per execution | ~15-20 min (75th percentile) | Medium |

---

## 2. Day 0 Checklist

**These are blocking.** Do not write code until all items are resolved or consciously accepted.

### Must Complete (2-3 hours)

- [ ] **Verify Groq RPD limit.** Run a test script that makes 5 API calls and reads the
  `x-ratelimit-limit-requests` HTTP response header. Record the actual number. This determines
  whether quota management uses conservative (1,000 RPD) or relaxed (14,400 RPD) mode.
  Script: `curl -s -D- https://api.groq.com/openai/v1/chat/completions -H "Authorization: Bearer $GROQ_API_KEY" -H "Content-Type: application/json" -d '{"model":"llama-3.3-70b-versatile","messages":[{"role":"user","content":"hi"}]}' 2>&1 | grep -i x-ratelimit`

- [ ] **Verify Cerebras account setup.** Create account at inference.cerebras.ai. Confirm:
  (a) API key obtained, (b) no credit card required, (c) Llama 3.3 70B available,
  (d) `json_schema` or equivalent structured output mode supported. Record actual rate limits
  from response headers or docs.

- [ ] **Audit top 10 competitors for scrapability.** For each of the founder's top 10 competitor
  names, manually check:
  (a) Does the website have a news/blog/press section?
  (b) Does it load without JavaScript (test with `curl`)?
  (c) Is there an RSS feed (check `/feed`, `/rss`, page source)?
  (d) Does Cloudflare or similar block automated access?
  Record results in a spreadsheet. If fewer than 8 of 10 have scrapable content, shift strategy
  to SERP-primary monitoring (changes architecture -- see Risk Register R2).

- [ ] **Get competitor list from founder.** Need: 15-30 company names with tier assignments
  (1 = direct competitor, 2 = adjacent, 3 = emerging). This is blocking for Week 1.

- [ ] **Confirm brief language.** English or Italian? CLAUDE.md says "all LLM prompts in English"
  but the founder may need Italian output.

- [ ] **Verify Gemini 2.5 Flash-Lite is not deprecated.** Gemini 2.0 Flash-Lite is deprecated
  (shutdown June 1, 2026). Confirm that 2.5 Flash-Lite is a separate, active model. If not,
  use Gemini 2.5 Flash for both classification fallback and brief generation.
  [DECISION NEEDED] Set a calendar reminder for June 1, 2026 to re-check.

### Should Complete (1-2 hours)

- [ ] **Telegram bot setup.** Create bot via @BotFather, get token, send a test message,
  record `chat_id`. Decide: founder-only (whitelist single `chat_id`) or group chat?
  [DECISION NEEDED]

- [ ] **Resend domain verification.** Resend requires DNS TXT record for production sending.
  Without it, emails send from `onboarding@resend.dev` and likely go to spam. Founder needs
  DNS access to add the TXT record. If DNS access is not available, email delivery works but
  may land in spam.

- [ ] **Decide: public or private repo?** Public = unlimited GH Actions minutes (eliminates
  biggest CI risk). Private = 2,000 min/month limit. Code is not a competitive secret; all
  secrets are encrypted via GitHub Secrets. [DECISION NEEDED]

---

## 3. Revised Stack Table

| Component | Tool | Free Tier Limits | Confidence |
|---|---|---|---|
| Web Scraping | Crawl4AI v0.8.6 (pinned) | Unlimited (open source) | High |
| RSS Parsing | feedparser + newspaper4k | Unlimited (open source) | High |
| SERP | Serper.dev | 2,500 queries/month | High |
| LLM Primary | Groq (Llama 3.3 70B) | 1,000 RPD, 30 RPM, 12,000 TPM (VERIFIED) | High |
| LLM Fallback 1 | Cerebras (Qwen 3 235B) | 14,400 RPD, 30 RPM, 1M TPD (VERIFIED) | High |
| LLM Fallback 2 | Gemini 2.5 Flash-Lite | ~1,000 RPD, 250K TPM (verify not deprecated) | Medium |
| Brief Generation | Gemini 2.5 Flash | 250 RPD, 1M context window | High |
| Database | Neon Postgres | 0.5 GB storage, 100 CU-hrs/month | High |
| Scheduling | GitHub Actions cron | 2,000 min/month (private), unlimited (public) | High |
| Delivery Primary | Telegram Bot API via httpx | Unlimited | High |
| Delivery Email | Resend | 3,000/month, 100/day | High |
| Python Packages | uv | N/A | High |
| Retry/Circuit Breaker | tenacity + circuitbreaker (or pybreaker) | N/A | Medium |
| Telegram Markdown | telegramify-markdown | N/A | Medium |
| Full Briefs | Telegraph API (telegra.ph) | Undocumented, no SLA | Low |

**Notes:**
- Cerebras RPD: no published daily limit. The 30 RPM figure implies ~43,200 req/day at
  continuous max rate, but actual limits may be lower. The "~1,440 RPD" figure used in the
  synthesis is UNVERIFIED and the derivation is unclear. Do not depend on this number.
- Mailgun: the synthesis claimed "5,000/month permanent free tier." This is WRONG. Per
  01_tech_stack_evaluation.md, Mailgun offers 1,000/month for 3 months only, then $35/month.
  Mailgun is not a viable free-tier backup. Stick with Resend.
- Telegraph: undocumented API with no SLA. Has 64KB content limit. If Telegraph is unreliable,
  fall back to sending the full brief as a Telegram document (PDF or HTML file upload).
- `circuitbreaker` package: last released 2023 (v1.4.0). Verify compatibility with Python 3.12+
  and async code. Alternative: `pybreaker`. [DECISION NEEDED] during Week 1 implementation.

---

## 4. Architecture Diagram

```
GitHub Actions Cron (06:17, 12:17, 18:17 UTC)
  |
  v
Pipeline Python (asyncio.Queue stages)
  |
  +-- Stage 1: SCRAPE (10 concurrent via arun_many)
  |     Crawl4AI v0.8.6 (stealth, PruningContentFilter)
  |     + feedparser/newspaper4k for RSS
  |     asyncio.Queue(maxsize=20) --> Stage 2
  |
  +-- Stage 2: DEDUP
  |     SHA256 content_hash, batch check vs Neon
  |     ON CONFLICT DO NOTHING. ~40-60% drop rate.
  |     asyncio.Queue(maxsize=10) --> Stage 3
  |
  +-- Stage 3: CLASSIFY (3 concurrent workers, batches of 3-5)
  |     Groq (json_schema mode)
  |       -> Cerebras fallback (on 429 or 80% daily quota)
  |       -> Gemini Flash-Lite fallback (on Cerebras failure)
  |     tenacity: wait_exponential_jitter, max 3 attempts per provider
  |     Circuit breaker: 5 failures -> open -> 30s half-open
  |     Pydantic validation at each boundary
  |
  +-- Stage 4: ENRICH + STORE (sequential)
  |     Entity linking via pg_trgm fuzzy match (threshold 0.6)
  |     asyncpg via Neon pooled connection (-pooler)
  |     Single transaction: UPSERT companies/contacts, INSERT signals
  |
  +-- Stage 5: BRIEF GENERATION (sequential, once per day)
  |     Gemini 2.5 Flash (250 RPD, 1M context)
  |     Feed all score>=3 signals in one request
  |     Save to briefs table
  |
  +-- Stage 6: DELIVER
        Telegram: summary (max 2,000 chars) + Telegraph link
        Email: full HTML brief via Resend (always, not fallback)
        Score-5 alerts: max 3/day, quiet hours 22:00-06:00 local

Data Layer:
  Neon Postgres (6 tables, pg_trgm, jsonb_path_ops GIN indexes)
  Read-only role for future NL-to-SQL (Phase 2)
  asyncpg, pooled connection string

Monitoring:
  scrape_logs table populated every run
  Telegram alert on pipeline failure (try/except in main.py)
  Dead man's switch: if no brief by 07:00 UTC, founder knows

Future (Phase 2):
  NL-to-SQL via Telegram bot commands (hybrid: templates + LLM)
  Streamlit dashboard on Community Cloud (if visual exploration needed)
  Keep-alive workflow to prevent 60-day GH Actions auto-disable
```

### Key Architectural Changes from Original Specs

1. No Vercel/Next.js -- eliminated due to commercial use prohibition.
2. Queue-based pipeline with backpressure between stages (was flat sequential).
3. Three-tier LLM fallback: Groq -> Cerebras -> Gemini (was Groq -> Gemini).
4. Gemini Flash reserved for brief generation (higher quality narrative).
5. Telegraph for full briefs with summary in Telegram (cap 2,000 chars, not 4,096).
6. Email always sent for daily briefs (was fallback-only).
7. Telegram alert caps: max 3 score-5 alerts/day, quiet hours enforced.

---

## 5. Sprint Plan

**Context:** 1 developer + AI assistant. 3 weeks. ~15-20 hrs/week effective.
Total budget: 45-60 hours. Plan targets 50 hours with explicit cut line.

### Week 1: Foundation + End-to-End Smoke Test (18h)

The Week 1 demo is a TRUE end-to-end test, not just scrape+classify+stdout. It validates
every integration point early (per red team recommendation).

| Task | Hours | Description |
|---|---|---|
| Repository setup | 2 | pyproject.toml (uv), .env.example, competitors.yaml (3 test), CLAUDE.md update |
| Neon DB provisioning | 1 | Create project, apply 001_initial.sql, enable pg_trgm, save secrets |
| Config module | 1 | pipeline/config.py: Pydantic BaseSettings, all env vars typed, incl. CEREBRAS_API_KEY |
| Crawl4AI scraper | 4 | pipeline/scraper/web.py: arun_many(), MemoryAdaptiveDispatcher(max_session_permit=5) |
| RSS parser | 2 | pipeline/scraper/rss.py: feedparser + newspaper4k |
| LLM client (3-tier) | 3 | pipeline/classifier/llm.py: Groq->Cerebras->Gemini. json_schema. tenacity. circuit breaker. |
| Signal classifier | 3 | pipeline/classifier/categorizer.py + scorer.py + prompts.py. Batch 3-5. Pydantic output. |
| E2E smoke test | 2 | Scrape 3 competitors -> classify -> store in Neon -> generate 1-signal brief -> send via Telegram. Validates ALL integration points. |

**Week 1 total: 18h.**
**Milestone:** `python -m pipeline.main demo` runs end-to-end locally. Brief arrives on Telegram.
All three LLM providers tested with at least one real API call.

### Week 2: Full Pipeline + Delivery (19h)

| Task | Hours | Description |
|---|---|---|
| Competitor research (5 real) | 3 | Find URLs, RSS, SERP queries for 5 tier-1 competitors. Validate scraping. |
| Content dedup | 2 | pipeline/enrichment/dedup.py: SHA256, batch check vs DB |
| Entity extraction + linking | 3 | Integrated into classification prompt. pipeline/enrichment/linker.py: pg_trgm. |
| Storage module | 2 | pipeline/storage/db.py: asyncpg connection pool, UPSERT helpers |
| Brief generator | 3 | pipeline/brief/generator.py: Gemini 2.5 Flash, score>=3 signals |
| Telegram delivery | 2 | pipeline/delivery/telegram.py: httpx, telegramify-markdown, Telegraph |
| Pipeline orchestrator | 2 | pipeline/main.py: run_daily() with asyncio.Queue stages, failure alert |
| GH Actions cron + cache | 1 | daily_pipeline.yml at :17. Playwright cache. astral-sh/setup-uv@v7. |

**Week 2 total: 18h.**
**Milestone:** Brief arrives on Telegram AND email from GH Actions cron, using 5 real competitors.
Pipeline runs 3x/day automatically.

### Week 2 Checkpoint (RED TEAM RECOMMENDED)

At end of Week 2, evaluate: is the pipeline producing useful briefs? If yes, proceed to Week 3.
If not, spend Week 3 fixing pipeline quality instead of adding features. The pipeline producing
good briefs is more valuable than any Week 3 feature.

### Week 3: Hardening + More Competitors (15h)

**Scope cut applied:** NL-to-SQL, Telegram bot commands, and SERP weekly scan moved to Phase 2.
Week 3 focuses on making the MVP reliable, tested, and documented.

| Task | Hours | Description |
|---|---|---|
| Additional competitor research (10 more) | 4 | Target: 15 total competitors (not 30). ~24 min each incl. validation. |
| Unit tests | 4 | Tests for dedup, classifier (mock LLM), linker, brief generator. pytest -x. |
| Integration test | 3 | test_e2e.py: full pipeline on 3 test competitors. Mock 429 to test fallback. |
| Scrape logging | 1 | scrape_logs table population with per-run metrics |
| Pipeline failure alerts | 0.5 | try/except in main.py -> Telegram alert on failure |
| Dead man's switch | 0.5 | Simple check: if no brief row for today by 07:00 UTC, send alert |
| Operator runbook | 2 | How to add competitors, debug failures, rotate secrets, re-run manually |

**Week 3 total: 15h.**
**Milestone:** System operational with 15 competitors, all tests passing, runbook delivered.

### Grand Total: 52h (within 45-60h envelope)

**Buffer:** 8h of slack within the 60h ceiling. This is for debugging, environment issues,
founder response latency, and integration surprises.

### Stretch Goals (only if ahead of schedule)

| Item | Hours | Prerequisite |
|---|---|---|
| Remaining 15 competitors (to reach 30) | 6 | Week 3 core complete |
| Weekly SERP scan | 2 | Pipeline stable |
| Keep-alive GH Actions workflow | 0.5 | Repo is public |
| NL-to-SQL query templates (5 hardcoded) | 3 | Pipeline stable |

---

## 6. LLM Provider Strategy

### The Groq RPD Contradiction

The original specs (01_tech_stack_evaluation.md) state Groq was **reduced** from 14,400 to
1,000 RPD "da inizio 2026." Agent 02's research found ~14,400 RPD via HTTP headers in
March 2026. These are contradictory. Both sources have credibility issues:

- The spec document was written for this project and explicitly references the reduction.
- The HTTP header observation is a single data point that Groq does not contractually guarantee.

**Resolution:** The actual RPD limit is **UNVERIFIED**. The Day 0 checklist includes a
verification step. The plan below works for BOTH scenarios.

### Scenario A: Groq RPD = 14,400 (best case)

- ~200 req/day needed = 1.4% of quota. Massive headroom.
- TPM (6,000) remains the binding constraint. Batch 3-5 signals.
- Cerebras and Gemini are insurance only.
- Development/testing can freely use Groq without quota concern.

### Scenario B: Groq RPD = 1,000 (conservative case)

- ~200 req/day needed = 20% of quota. Workable but tight.
- Development/testing during Weeks 1-3 will consume ~100-200 RPD/day on top of production.
  Solution: use Cerebras for development, reserve Groq for production runs.
- At 80% quota (800 req), automatically route to Cerebras.
- Brief generation uses Gemini Flash (not Groq), saving ~5-10 req/day.
- NL-to-SQL (Phase 2) shares the same quota. With templates handling 60-70% of queries,
  LLM queries use ~5-10 req/day max. Acceptable.
- Retries consume quota. Set max retries to 2 (not 3) per request.
- **Error budget for dev:** reserve a separate API key for development if Groq allows it.
  Otherwise, do all prompt development against Cerebras.

### Fallback Chain Logic

```
Request --> Groq
              |
              +--> 429 or quota >= 80% daily
              |         |
              |         v
              |    Cerebras
              |         |
              |         +--> 429 or timeout > 10s
              |         |         |
              |         |         v
              |         |    Gemini 2.5 Flash-Lite (classification)
              |         |    Gemini 2.5 Flash (brief generation)
              |         |
              |         +--> Success --> return
              |
              +--> Success --> return
```

Each provider uses:
- `tenacity`: `wait_exponential_jitter(initial=1, max=30)`, max 2 retries per provider
- Circuit breaker: 5 consecutive failures -> open -> 30s half-open
- `json_schema` response format (Groq, Cerebras). Verify Cerebras supports this on Day 0.
  If not, use `json_object` with Pydantic post-validation.

### Quota Tracking

On every response, read and log:
- `x-ratelimit-remaining-requests` (RPD remaining)
- `x-ratelimit-remaining-tokens` (TPM remaining)

Store in memory. Switch provider at 80% consumption of either limit.

### Combined Daily Capacity (all providers)

| Provider | RPD | TPM | Notes |
|---|---|---|---|
| Groq | 1,000-14,400 | 6,000 | UNVERIFIED RPD |
| Cerebras | UNVERIFIED | 60,000 | No published RPD. 30 RPM = max ~43,200/day at continuous use. |
| Gemini Flash-Lite | ~1,000 | 250,000 | Verify not deprecated (2.0 is, 2.5 may not be) |
| Gemini Flash | 250 | 1,000,000 | Reserved for brief generation |
| **Combined** | **>2,250 minimum** | **>316,000** | Even worst case, >10x daily need |

---

## 7. Pipeline Architecture

### Module Breakdown

```
pipeline/
  __init__.py
  main.py                  # Orchestrator: run_daily(), run_demo()
  config.py                # Pydantic BaseSettings, all env vars typed

  scraper/
    __init__.py
    web.py                 # Crawl4AI: arun_many(), stealth, PruningContentFilter
    rss.py                 # feedparser + newspaper4k
    registry.py            # Load/validate competitors.yaml

  enrichment/
    __init__.py
    dedup.py               # SHA256 content hash, batch check vs DB
    linker.py              # Entity -> companies/contacts via pg_trgm fuzzy match

  classifier/
    __init__.py
    llm.py                 # 3-tier client: Groq->Cerebras->Gemini. Retry+circuit breaker.
    categorizer.py         # category enum classification
    scorer.py              # relevance score 1-5
    prompts.py             # All prompt templates (system + few-shot)

  storage/
    __init__.py
    db.py                  # asyncpg connection pool, UPSERT helpers
    models.py              # Pydantic models for each table
    migrations/
      001_initial.sql      # Full schema

  brief/
    __init__.py
    generator.py           # Gemini 2.5 Flash, query score>=3 signals
    templates.py           # Brief prompt templates (Battlefield Brief format)

  delivery/
    __init__.py
    telegram.py            # httpx direct, telegramify-markdown, Telegraph for full briefs
```

### Key Implementation Details

**Scraping (web.py):**
- Use `asyncio.gather(return_exceptions=True)` (not `TaskGroup`) for partial results on failure.
- `arun_many()` with `MemoryAdaptiveDispatcher(max_session_permit=5)` for memory-safe concurrency.
- Rate limit: 2s delay between requests to same domain.
- For static HTML pages (no JS needed): fast path via `httpx + BeautifulSoup` to save Playwright
  overhead. Determine which pages are static during Day 0 competitor audit.

**Classification (categorizer.py):**
- Use `json_schema` response format (not `json_object`). This provides strict schema enforcement.
  The original spec (03_backlog.md) incorrectly specifies `json_object`.
- Categories (opportunity-focused for Green Growth's ICP):
    - `precision_ag_adoption` — target company adopts precision ag tools, data platforms, sensors
    - `sustainability_initiative` — ESG commitments, regenerative ag, carbon credits, GHG targets
    - `tech_investment` — digital transformation, AgTech partnerships, R&D spend
    - `vendor_search` — RFPs, vendor evaluations, supplier program launches
    - `expansion` — new acreage, facilities, markets, production scale-up
    - `leadership_change` — new CTO, VP Agronomy, digital ag lead (potential champion)
    - `partnership` — alliances, integrations, distribution deals with other AgTech
    - `funding_m_and_a` — investment rounds, acquisitions, IPOs (indicates budget)
    - `other` — anything noteworthy that doesn't fit above
  Relevance score 1-5 = how strongly the signal indicates a sales opportunity for Green Growth.
    5 = direct buying signal (e.g., "McCain launches precision ag supplier program")
    4 = strong indicator (e.g., "Simplot invests in yield monitoring R&D")
    3 = moderate relevance (e.g., "Lamb Weston expands processing capacity")
    2 = weak relevance (e.g., "Corteva hires new marketing VP")
    1 = noise (e.g., "Bayer sponsors golf tournament")
- Batch 3-5 signals per request. Accuracy degrades beyond 5 items per prompt.
- Include 5-8 few-shot examples in prompts.py.
- Pydantic model validates every response. Invalid responses are logged and retried once.

**Brief (generator.py):**
- Uses Gemini 2.5 Flash (not Groq). 1M context window fits all daily signals.
- Generates once per day (on the 18:17 UTC run, or the first run with score>=3 signals).
- Structure: Executive Summary, top opportunities (score 4-5), signals by category,
  Key Takeaways, Suggested Actions (specific outreach recommendations for Green Growth).
- Context: the prompt must include Green Growth's product description (retrofit yield monitors
  for combines and potato harvesters) so the AI can assess opportunity relevance.
- Target: 500-1,500 words.

**Delivery (telegram.py):**
- Telegram message capped at 2,000 characters (not 4,096) to avoid message fatigue.
- Full brief published to Telegraph; summary + link sent via Telegram.
- Score-5 alerts: max 3/day, quiet hours 22:00-06:00 local time (configurable).
- If Telegraph is down: send full brief as a document (PDF or txt file upload).

---

## 8. Delivery Strategy

### Telegram (Primary, Real-Time)

| Message Type | When | Content | Cap |
|---|---|---|---|
| Daily Brief Summary | After 18:17 UTC run (or first run with signals) | 2,000 char summary + Telegraph link | 1/day |
| Score-5 Alert | Immediately after classification | Competitor, category, summary, source URL | 3/day |
| Pipeline Failure | On exception | Error type, failed step, timestamp | No cap |
| Dead Man's Switch | If no brief by 07:00 UTC | "No brief generated today -- check pipeline" | 1/day |

**Security:** Whitelist founder's `chat_id`. Reject messages from unknown chat IDs.

**Implementation:** Raw `httpx.AsyncClient` (not `python-telegram-bot`). For send-only use,
httpx is simpler and avoids a heavy dependency. If interactive bot commands are added (Phase 2),
upgrade to `python-telegram-bot` at that point.

**MarkdownV2 escaping:** Use `telegramify-markdown` library to convert standard Markdown to
Telegram-safe format. Manual escaping is error-prone (even `.` must be escaped).

### Email — REMOVED

Email delivery was cut per founder's approved overview ("zero additional value").
Resend remains in the stack table as a Phase 2 option if the founder later wants email archival.

### Telegraph (Full Brief Hosting)

Full briefs published to Telegraph (telegra.ph) for Instant View reading experience.
Telegram summary links to the Telegraph page.

**Risk:** Telegraph is an unofficial/semi-official API with no SLA. It has a 64KB content limit.
**Fallback:** If Telegraph is unavailable, send the full brief as a file attachment via Telegram.

---

## 9. Database Schema

The schema from 02_architecture.md is confirmed. No changes needed.

### 6 Tables

| Table | Purpose | Year 1 Rows |
|---|---|---|
| targets | 15-21 monitored target companies (Green Growth's ICP) | 15-21 |
| companies | All companies mentioned in signals | ~300 |
| contacts | People with role/company | ~600 |
| signals | Classified signals (core data) | ~5,000-10,000 |
| briefs | Daily brief archive | ~365 |
| scrape_logs | Per-run health metrics | ~1,100 |

### Indexes

| Index | Type | Purpose |
|---|---|---|
| idx_signals_content_hash | UNIQUE B-tree | Dedup enforcement |
| idx_signals_competitor_date | B-tree (composite) | Timeline queries |
| idx_signals_category | B-tree | Category filtering |
| idx_signals_score | B-tree | Score filtering |
| idx_signals_entities | GIN (jsonb_path_ops) | Entity search (compact) |
| idx_companies_name_trgm | GIN (gin_trgm_ops) | Fuzzy company name search |
| idx_contacts_name_trgm | GIN (gin_trgm_ops) | Fuzzy contact name search |
| idx_contacts_company | B-tree | Company-contact join |
| idx_briefs_date | B-tree (DESC) | Latest brief lookup |
| idx_scrape_logs_date | B-tree (DESC) | Recent logs |

### Storage Projections

- Raw data: ~20 MB/year (signals text + metadata)
- GIN indexes (jsonb_path_ops + pg_trgm): ~10-30 MB (using compact jsonb_path_ops, not default)
- Total Year 1: ~30-50 MB (6-10% of 500 MB limit)
- Break-even: Year 8-10 at current ingestion rate
- Storage is a non-issue. Monitor with `pg_database_size()` but deprioritize.

### Read-Only Role (for Phase 2 NL-to-SQL)

```sql
CREATE ROLE greenscan_readonly WITH LOGIN PASSWORD 'xxx';
GRANT CONNECT ON DATABASE neondb TO greenscan_readonly;
GRANT USAGE ON SCHEMA public TO greenscan_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO greenscan_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO greenscan_readonly;
```

Set up during Week 1 DB provisioning. Not used until Phase 2.

---

## 10. GitHub Actions Configuration

### `daily_pipeline.yml`

```yaml
name: Daily Pipeline
on:
  schedule:
    # Run at :17 past the hour to avoid cron congestion at :00
    - cron: '17 6,12,18 * * *'
  workflow_dispatch:

jobs:
  pipeline:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4

      - name: Setup uv
        uses: astral-sh/setup-uv@v7
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: uv sync

      - name: Setup Crawl4AI
        run: uv run crawl4ai-setup

      # Cache Playwright browsers to save ~1-3 min/run
      - name: Cache Playwright browsers
        id: playwright-cache
        uses: actions/cache@v4
        with:
          path: ~/.cache/ms-playwright
          key: playwright-${{ hashFiles('uv.lock') }}

      - name: Install Playwright (cache miss only)
        if: steps.playwright-cache.outputs.cache-hit != 'true'
        run: uv run playwright install chromium --with-deps

      - name: Install Playwright deps (cache hit)
        if: steps.playwright-cache.outputs.cache-hit == 'true'
        run: uv run playwright install-deps chromium

      - name: Run pipeline
        run: uv run python -m pipeline.main daily
        env:
          DATABASE_URL: ${{ secrets.NEON_DATABASE_URL }}
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
          CEREBRAS_API_KEY: ${{ secrets.CEREBRAS_API_KEY }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
```

### `weekly_deep_scan.yml` (Phase 2, not in MVP)

```yaml
name: Weekly Deep Scan
on:
  schedule:
    - cron: '17 4 * * 0'    # Sunday 04:17 UTC
  workflow_dispatch:

jobs:
  deep-scan:
    runs-on: ubuntu-latest
    timeout-minutes: 45
    steps:
      - uses: actions/checkout@v4

      - name: Setup uv
        uses: astral-sh/setup-uv@v7
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: uv sync

      - name: Setup Crawl4AI
        run: uv run crawl4ai-setup

      - name: Cache Playwright browsers
        id: playwright-cache
        uses: actions/cache@v4
        with:
          path: ~/.cache/ms-playwright
          key: playwright-${{ hashFiles('uv.lock') }}

      - name: Install Playwright (cache miss only)
        if: steps.playwright-cache.outputs.cache-hit != 'true'
        run: uv run playwright install chromium --with-deps

      - name: Install Playwright deps (cache hit)
        if: steps.playwright-cache.outputs.cache-hit == 'true'
        run: uv run playwright install-deps chromium

      - name: Run weekly scan
        run: uv run python -m pipeline.main weekly
        env:
          DATABASE_URL: ${{ secrets.NEON_DATABASE_URL }}
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
          CEREBRAS_API_KEY: ${{ secrets.CEREBRAS_API_KEY }}
          SERPER_API_KEY: ${{ secrets.SERPER_API_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
```

### CI Minutes Budget

| Workflow | Runtime (p75) | Frequency | Monthly Minutes |
|---|---|---|---|
| Daily Pipeline | 18 min | 3x/day, 30 days | 1,620 |
| CI (test on push) | 3 min | ~20 pushes/month | 60 |
| **Total (MVP)** | | | **~1,680** |
| Weekly Deep Scan (Phase 2) | 20 min | 4x/month | 80 |
| **Total (with Phase 2)** | | | **~1,760** |

At 1,680 min/month, this is 84% of the 2,000 min private repo limit. This is tight.

**Mitigations (in priority order):**
1. Make repo public (unlimited minutes). [DECISION NEEDED]
2. Cache Playwright browsers (saves ~1-3 min/run = 90-270 min/month).
3. Use `uv sync` instead of `pip install` (saves ~30-60s/run = 45-90 min/month).
4. Skip Crawl4AI for static pages (httpx fast path, saves ~2-3 min/run).
5. Reduce to 2x/day if minutes exceed 80% by mid-month.

### GitHub Secrets Required

| Secret | Source |
|---|---|
| NEON_DATABASE_URL | Neon dashboard -> Connection Details (pooled) |
| GROQ_API_KEY | console.groq.com -> API Keys |
| CEREBRAS_API_KEY | inference.cerebras.ai -> API Keys |
| GEMINI_API_KEY | aistudio.google.com -> Get API Key |
| SERPER_API_KEY | serper.dev -> Dashboard |
| TELEGRAM_BOT_TOKEN | @BotFather on Telegram |
| TELEGRAM_CHAT_ID | Send message to bot, use getUpdates API |
| RESEND_API_KEY | resend.com -> API Keys (Phase 2, not needed for MVP) |

---

## 11. Risk Register

Incorporating all mitigations from both reviews.

| # | Risk | S | L | Score | Mitigation | Status |
|---|---|---|---|---|---|---|
| R1 | **Groq RPD is actually 1,000 (not 14,400)** | 5 | 4 | 20 | Day 0 verification via HTTP headers. Plan works for both scenarios (Section 6). Conservative quota management (80% threshold). Cerebras + Gemini provide >1,250 RPD additional capacity. | Verify Day 0 |
| R2 | **Competitors are not scrapable** | 5 | 4 | 20 | Day 0 audit of top 10 competitors. If <8 have scrapable content, shift to SERP-primary monitoring (increase Serper.dev usage, still within 2,500/month). This changes architecture. | Verify Day 0 |
| R3 | **Timeline too tight for 1 dev** | 4 | 4 | 16 | Week 3 scope cut by 35% (NL-to-SQL, bot commands moved to Phase 2). Target 15 competitors not 30. Week 2 checkpoint: if pipeline not producing briefs, cut all Week 3 features. | Mitigated |
| R4 | **Integration failures discovered late** | 4 | 3 | 12 | Week 1 demo is true E2E (scrape->classify->store->brief->deliver), not just scrape+stdout. Validates all integration points in Week 1. | Mitigated |
| R5 | **Post-handoff system degrades silently** | 4 | 3 | 12 | Dead man's switch (alert if no brief by 07:00). Operator runbook (2h). scrape_logs for diagnostics. Monthly 15-min check-in for first 3 months. | Mitigated |
| R6 | **GH Actions cron stops after 60 days inactivity** | 3 | 3 | 9 | Phase 2: keep-alive workflow (weekly `echo "alive"` + external cron trigger). For MVP: founder commits competitors.yaml changes to keep repo active. | Partially mitigated |
| R7 | **LLM providers reduce free tiers simultaneously** | 4 | 2 | 8 | 3 independent providers. Combined capacity >10x daily need even in worst case. Monthly limit monitoring. If all three restrict: Groq Dev tier is $0.10/1K tokens (~$3/month at current volume). | Mitigated |
| R8 | **Crawl4AI breaking changes** | 3 | 3 | 9 | Pin exact version (0.8.6). Test before bumping. Risk: frozen on security fixes. Playwright update incompatibility is the specific failure mode (see red team F4). | Accepted |
| R9 | **Telegram message overload** | 3 | 3 | 9 | Cap brief summary at 2,000 chars. Cap score-5 alerts at 3/day. Quiet hours 22:00-06:00. Full brief on Telegraph, not in Telegram. | Mitigated |
| R10 | **Cerebras integration harder than expected** | 3 | 3 | 9 | Day 0 verification of account setup, API key, json_schema support. If Cerebras does not support structured output, use json_object + Pydantic post-validation. Budget 1-2h dedicated integration work in Week 1. | Verify Day 0 |

---

## 12. Open Questions

### Blocking (must resolve before Week 1)

1. **[DECISION NEEDED] Public or private repo?** Public = unlimited GH Actions minutes, eliminates
   R3/R6. Private = 2,000 min/month, tight at ~1,680 projected. Secrets remain safe either way.
   Recommendation: go public.

2. ~~**[RESOLVED] Target company list.**~~ 21 companies provided via CSV (US Agriculture
   Operators). 10 HIGH priority, 11 MEDIUM. Use all 21 — they are the ICP, not generic competitors.

3. **[DECISION NEEDED] Telegram access model.** Restrict to founder's `chat_id` only, or a
   group chat? Determines whitelist logic.

4. ~~**[RESOLVED] Brief language.**~~ English. Confirmed by founder.

5. ~~**[RESOLVED] GDPR.**~~ No GDPR considerations for now. Revisit if needed.

### Non-Blocking (resolve during development)

6. **Groq RPD verification.** Day 0 task. Result determines Scenario A vs B (Section 6).

7. **Cerebras structured output support.** Day 0 task. If `json_schema` not supported,
   use `json_object` + Pydantic validation.

8. **Gemini 2.5 Flash-Lite deprecation status.** Verify it is not the same model as the
   deprecated 2.0 Flash-Lite. If it is deprecated, use Gemini 2.5 Flash for both classification
   fallback and brief generation (reduces from 1,000 to 250 RPD for classification fallback).

9. **Telegraph API reliability.** Test on Day 0 or Week 1. If unreliable, use Telegram file
   upload as fallback.

10. **`circuitbreaker` vs `pybreaker` for async Python 3.12+.** Evaluate during Week 1
    LLM client implementation. `circuitbreaker` last released 2023. `pybreaker` may be
    better maintained.

11. **Crawl4AI `crawl4ai-setup` vs `playwright install`.** Does `crawl4ai-setup` replace
    `playwright install chromium --with-deps`, or supplement it? Test in CI during Week 1.
    Does it respect `PLAYWRIGHT_BROWSERS_PATH` for caching?

12. ~~**Resend domain verification.**~~ Not needed — email removed from MVP.

13. **Vercel commercial use -- is it actually a showstopper?** If the founder is unpaid and the
    tool is internal (not revenue-generating), the Hobby plan prohibition may not apply. Worth
    a closer legal reading before permanently eliminating the frontend option. Not blocking for
    MVP since Telegram+email covers needs. [DECISION NEEDED] for Phase 2 planning.

---

## 13. Phase 2 Backlog

Items cut from MVP and the reason for cutting them.

| Item | Original Plan | Why Cut | When to Revisit |
|---|---|---|---|
| NL-to-SQL (hybrid) | Week 3, 4h | Week 3 overloaded. Complex multi-component system (templates, intent routing, LLM fallback, validation, evaluation). 4h was unrealistic. | After 2 weeks of live operation. Start with 5 hardcoded query templates. |
| Telegram bot commands | Week 3, 2h | Requires upgrading from httpx to python-telegram-bot (contradicts "start simple" decision). Depends on NL-to-SQL. | After NL-to-SQL is built. |
| Weekly SERP scan | Week 3, 1h | Pipeline not yet proven. SERP value unvalidated. | After validating pipeline produces useful briefs with direct scraping. |
| Next.js frontend | Week 3 (original) | Vercel commercial use ban. Over-engineered for 1-3 users. | When paying users exist. Deploy on Cloudflare Pages with Next.js 15+. |
| Streamlit dashboard | Not in original | Pipeline + Telegram covers 90% of needs. | After 30 days of operation, if visual data exploration is needed. |
| Remaining 15 competitors (to 30) | Week 3, 4h | 15 competitors is sufficient for MVP. Expanding to 30 is mechanical work. | Week 4+, as stretch or ongoing maintenance. |
| Cross-signal correlation | Stretch | Needs 30+ days of signal history. | After 30 days of data accumulation. |
| Activity heatmap | Stretch | Needs frontend. | With Streamlit or frontend. |
| Contacts CRUD UI | Stretch | No frontend. Contacts auto-populated by pipeline. | When manual contact management becomes a need. |
| Keep-alive workflow | Week 3 | Not needed until repo is >60 days old with no commits. | Month 2 of operation. |
| 60-day GH Actions inactivity guard | Not planned | Relevant only for public repo. | When/if repo goes public. |

### Phase 2 Priority Order (recommended)

1. NL-to-SQL with query templates (highest user value)
2. Expand to 30 competitors (mechanical)
3. Weekly SERP scan (additional signal source)
4. Telegram bot commands (/query, /competitor, /latest)
5. Streamlit dashboard (if visual exploration needed)
6. Keep-alive workflow (operational resilience)

---

## Document Supersession Notice

This document (12_final_plan.md) supersedes:

- **09_synthesis.md** -- integrated with corrections from both reviews.
- Relevant sections of **01_tech_stack_evaluation.md** through **04_recommended_stack_summary.md**
  regarding: Groq RPD limits, frontend stack, email delivery mode, pipeline architecture,
  and CI configuration.

**IMPORTANT:** Before writing code, update **CLAUDE.md** to reflect:
- Remove Next.js/Vercel/frontend references and commands.
- Change Groq RPD to "UNVERIFIED (1,000 or 14,400)."
- Add Cerebras as LLM Fallback 1.
- Replace `pip` references with `uv`.
- Update architecture description to match this plan.

The original spec files (01-04) should be marked with a header noting they are superseded by
this document, or archived to an `archive/` directory to prevent implementation confusion.
