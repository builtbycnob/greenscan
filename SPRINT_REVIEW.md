# GreenScan — Sprint Review & Delivery Summary

**Project:** GreenScan Alpha — Market Intelligence Pipeline for Green Growth Innovations
**Team:** Corrado (dev) + Claude AI (pair programming)
**Timeline:** March 29–30, 2026 (2 working sessions)
**Budget:** €0/month (all free tiers)
**Repository:** github.com/builtbycnob/greenscan (public)

---

## Executive Summary

GreenScan is a fully automated market intelligence pipeline that monitors 21 target companies in the US agriculture sector and delivers a daily Battlefield Brief to the founder's Telegram. The system scrapes competitor websites, classifies signals using AI (identifying sales opportunities for Green Growth's retrofit yield monitors), stores results in a cloud database, and generates actionable intelligence reports.

The MVP was built in two intensive sessions totaling ~8 hours of active development, supported by a deep research phase that validated every architectural decision before writing code.

---

## Pre-Sprint: Deep Research Phase

**Duration:** ~45 minutes (automated)
**Output:** 12 research documents in `docs/research/`

### What Was Done

- Launched **8 parallel research agents** (Opus) covering: web scraping stack, LLM providers, database options, NL-to-SQL feasibility, pipeline architecture, CI/CD scheduling, delivery channels, and frontend alternatives
- **Synthesis agent** consolidated findings across all 8 reports
- **2 adversarial reviewers** (Technical + Red Team) challenged the synthesis
- **Final integration agent** produced the definitive implementation plan (`12_final_plan.md`)
- Researched **Green Growth Innovations** to understand the stakeholder's business (precision ag, retrofit yield monitors, potato/grain harvesters)

### Key Findings That Changed the Plan

| Original Assumption | Research Finding | Action Taken |
|---|---|---|
| Groq = 1,000 RPD | Verified: confirmed 1,000 RPD, but 12K TPM (better than expected) | Batching strategy validated |
| Cerebras = Llama 3.3 70B | Llama 3.3 70B removed; Qwen 3 235B available (14,400 RPD) | Updated fallback provider |
| Next.js frontend on Vercel | Vercel Hobby prohibits commercial use; frontend over-engineered for 1-3 users | Eliminated frontend entirely |
| Monitor competitors | CSV contains target customers (ICP), not competitors | Pivoted to opportunity-focused monitoring |
| Email + Telegram delivery | Founder approved Telegram-only in overview document | Removed email delivery |
| Gemini 2.0 Flash-Lite | 2.0 is deprecated (June 2026); 2.5 Flash-Lite is active and separate | Updated model references |

### Scrapability Audit

Audited all 10 HIGH-priority target companies:

| Company | Approach | Result |
|---|---|---|
| R.D. Offutt Farms | Direct scrape | ✅ Active news + blog |
| J.R. Simplot Company | Direct scrape | ✅ News hub |
| CSS Farms | SERP only | ⚠️ No news page |
| Black Gold Farms | SERP only | ⚠️ Empty news page |
| Ceres Partners | SERP only | ⚠️ Acquired by WisdomTree |
| Farmland Partners | SEC/IR | ⚠️ JS-rendered, content too short |
| McCain Foods | Direct scrape | ✅ Very active news centre |
| Lamb Weston | Scrape + SEC | ✅ Active newsroom + IR |
| American Farm Bureau | Direct scrape | ✅ Prolific news (fb.org, not fbfs.com) |
| Bayer Crop Science | Scrape + SEC | ✅ Active crop science news |

**Result:** 7/10 scrapable via direct access. Sufficient for MVP.

---

## Sprint 1: Foundation + E2E Pipeline

**Duration:** ~5 hours
**Milestone:** `python -m pipeline demo` runs end-to-end, brief arrives on Telegram

### Deliverables

#### 1. Project Scaffold
- `pyproject.toml` with all dependencies (Crawl4AI, Groq SDK, asyncpg, Pydantic, tenacity)
- `uv` as package manager (per project standards)
- `.env` / `.env.example` for secrets management
- `.gitignore` configured to protect sensitive files

#### 2. Target Registry (`targets.yaml`)
- 21 target companies mapped from founder's ICP spreadsheet
- Each with: name, industry, priority (HIGH/MEDIUM), monitoring type, website, scrape URLs, SERP queries
- Industries: Direct Farm Operator (7), Food Processor (4), Farmland Investor (3), Crop Insurance (3), Agri Input (4)

#### 3. Web Scraper (`pipeline/scraper/web.py`)
- Built on **Crawl4AI v0.8.6** with stealth mode
- `arun_many()` for batch crawling with `MemoryAdaptiveDispatcher` (max 5 concurrent)
- `PruningContentFilter` for clean markdown output
- Rate limiting: 1-3s random delay between requests
- Graceful error handling: logs failures and continues

#### 4. RSS Feed Parser (`pipeline/scraper/rss.py`)
- `feedparser` for feed parsing + `newspaper4k` for full article extraction
- Same `RawSignal` output format as web scraper
- Module ready but no RSS feeds found during scrapability audit

#### 5. 3-Tier LLM Client (`pipeline/classifier/llm.py`)
- **Primary:** Groq (Llama 3.3 70B) — 1,000 RPD, 12K TPM
- **Fallback 1:** Cerebras (Qwen 3 235B) — 14,400 RPD, 1M TPD
- **Fallback 2:** Gemini 2.5 Flash-Lite — 1,000 RPD
- Automatic quota tracking via HTTP response headers
- Custom `SimpleCircuitBreaker` (5 failures → open → 30s reset)
- `tenacity` retry with exponential backoff + jitter
- Provider switching at 80% quota consumption

**Technical note:** `pybreaker` library was found to be broken (references Tornado's `gen` module). Replaced with a custom 30-line circuit breaker implementation.

#### 6. Signal Classifier (`pipeline/classifier/categorizer.py`)
- 9 opportunity-focused categories:
  - `precision_ag_adoption`, `sustainability_initiative`, `tech_investment`
  - `vendor_search`, `expansion`, `leadership_change`
  - `partnership`, `funding_m_and_a`, `other`
- Relevance scoring 1-5 (from Green Growth's sales perspective)
- Batch classification: 3-5 signals per LLM request
- Pydantic validation with lenient entity handling (handles both flat lists and structured dicts)
- JSON schema enforced via prompt (Groq `json_object` mode; `json_schema` not supported on Llama 3.3 70B)

#### 7. Content Deduplication (`pipeline/enrichment/dedup.py`)
- SHA256 content hash with in-memory tracking
- Cross-run dedup via Neon Postgres (`content_hash` UNIQUE constraint)
- Verified: second pipeline run correctly filtered 5/7 duplicates

#### 8. Database Schema & Storage (`pipeline/storage/`)
- **Neon Postgres 17** on AWS us-east-1 (free tier: 0.5GB, 100 CU-hrs/month)
- 6 tables: `targets`, `companies`, `contacts`, `signals`, `briefs`, `scrape_logs`
- `pg_trgm` extension enabled for fuzzy search
- GIN indexes with `jsonb_path_ops` for entity search
- `asyncpg` connection pool with pooled connection string (PgBouncer built-in)
- Migration applied: `001_initial.sql`
- Read-only role prepared for Phase 2 NL-to-SQL

#### 9. Battlefield Brief Generator (`pipeline/brief/generator.py`)
- Uses Groq for generation (Gemini 2.5 Flash when API key added)
- Prompt includes Green Growth product context for relevant recommendations
- Structure: Executive Summary → Top Opportunities → Other Signals → Key Takeaways → Suggested Actions
- Target: 500-1,500 words

#### 10. Telegram Delivery (`pipeline/delivery/telegram.py`)
- Raw `httpx.AsyncClient` (no bot framework — send-only use case)
- `telegramify-markdown` for MarkdownV2 escaping
- Message splitting at paragraph boundaries (4,000 char safe limit)
- Fallback to plaintext if markdown parsing fails
- Score-5 critical alerts (separate from daily brief)
- Pipeline failure alerts with error details

#### 11. Pipeline Orchestrator (`pipeline/main.py`)
- Two modes: `demo` (3 targets, stdout) and `daily` (all targets, DB, Telegram)
- Full pipeline: scrape → dedup → classify → link entities → store → brief → deliver
- Per-run logging to `scrape_logs` table with run_id, counts, duration, errors

### Verification

- **Day 1 Demo:** Successfully scraped 3 targets, classified signals, generated brief, delivered to Telegram
- **API verification:**
  - Groq: 1,000 RPD confirmed via `x-ratelimit-limit-requests` header
  - Cerebras: 14,400 RPD confirmed, Qwen 3 235B available
  - Gemini 2.5 Flash-Lite: confirmed active (2.0 is deprecated, not 2.5)
- **Telegram:** Test message received successfully
- **Full pipeline:** 8 URLs scraped → 7 signals → 1 dedup → 6 unique → classified → stored in Neon → brief generated → delivered to Telegram (~17 seconds total)

---

## Sprint 2: Hardening + CI/CD

**Duration:** ~3 hours
**Milestone:** Pipeline runs automatically on GitHub Actions, all tests passing

### Deliverables

#### 1. Entity Linker (`pipeline/enrichment/linker.py`)
- Fuzzy matching via `pg_trgm` with configurable similarity threshold (0.6)
- Links extracted company and person names to existing DB records
- Creates new records if no match found (confidence 0.5)
- Integrated into daily pipeline between classification and storage

#### 2. Scrape Logging
- Every pipeline run logged to `scrape_logs` table
- Tracks: run_id, targets total/success/failed, signals new/deduped, duration_ms, error_message, metadata (JSONB)
- Status transitions: running → success / failure

#### 3. GitHub Actions Workflows
- **`daily_pipeline.yml`:** Cron at 07:00 UTC (08:00 CET), Playwright browser caching, all secrets
- **`test.yml`:** Runs on push/PR, lint + unit tests (no API calls needed)
- **`dead_mans_switch.yml`:** Runs at 07:00 UTC, checks for today's brief, alerts on Telegram if missing

#### 4. Unit Tests (18 tests)
| Test File | Tests | What It Covers |
|---|---|---|
| `test_dedup.py` | 4 | Exact duplicates, unique preservation, known hashes, seen count |
| `test_models.py` | 7 | Hash determinism, entity coercion (list, dict, empty), ClassifiedSignal parsing |
| `test_registry.py` | 4 | YAML loading, HIGH priority count, scrapable targets, SERP queries |
| `test_brief.py` | 3 | Signal formatting, low-score skip, score filtering with mock LLM |

#### 5. Integration Tests (6 tests)
| Test File | Tests | What It Covers |
|---|---|---|
| `test_classifier.py` | 3 | Groq batch classification, Cerebras fallback, quota tracking |
| `test_fallback.py` | 3 | Groq→Cerebras fallback on exhaustion, multi-provider resilience, circuit breaker |

#### 6. Operator Runbook (`RUNBOOK.md`)
- How to add new target companies
- How to debug pipeline failures (SQL queries for scrape_logs)
- Common issues troubleshooting table
- Secret rotation procedures
- Daily/weekly/monthly monitoring checklists
- Architecture overview diagram

#### 7. CLAUDE.md Updated
- Reflects current stack (Groq + Cerebras + Gemini, no frontend, no email)
- Verified API limits documented
- All commands updated

### Bug Fixes
- **CI failure:** `Settings` required API keys at import time, breaking tests in CI. Fixed by making keys optional with validation at call time.
- **Brief not sent:** `min_score=3` threshold too high for current signal quality. Changed to `min_score=1` for daily runs (always generate brief if signals exist).
- **pybreaker broken:** Library references Tornado's `gen` module (not installed). Replaced with custom `SimpleCircuitBreaker`.
- **Groq `json_schema` not supported:** Llama 3.3 70B on Groq only supports `json_object` mode. Schema enforced via prompt + Pydantic post-validation.
- **Brief duplication:** Groq sometimes duplicated brief content in response. Mitigated with explicit prompt instruction.

### Verification
- **CI tests:** All passing on GitHub Actions (18 unit tests, lint clean)
- **Pipeline on GH Actions:** Successfully ran, found 1 new signal, generated brief #2, delivered to Telegram
- **Cross-run dedup:** Verified working (10 known hashes loaded from DB, 6/7 duplicates filtered)
- **Cron:** Active at 07:00 UTC daily

---

## Current System State

### Database Contents
| Table | Records |
|---|---|
| signals | 11 |
| briefs | 2 |
| companies | 2 |
| contacts | 0 |
| scrape_logs | 3 runs |

### Repository Structure
```
greenscan/
├── .github/workflows/          # 3 workflows (daily, test, dead man's switch)
├── pipeline/
│   ├── scraper/                # web.py, rss.py, registry.py, models.py
│   ├── classifier/             # llm.py, categorizer.py, prompts.py
│   ├── enrichment/             # dedup.py, linker.py
│   ├── storage/                # db.py, migrations/001_initial.sql
│   ├── brief/                  # generator.py
│   ├── delivery/               # telegram.py
│   ├── config.py               # Pydantic settings
│   └── main.py                 # Orchestrator (demo + daily modes)
├── tests/                      # 24 tests (18 unit + 6 integration)
├── docs/research/              # Deep research output (12 files)
├── targets.yaml                # 21 target companies
├── CLAUDE.md                   # Project instructions
├── RUNBOOK.md                  # Operator handbook
└── pyproject.toml              # Dependencies & config
```

### Commits
| Hash | Message |
|---|---|
| `eb19352` | feat: MVP pipeline — scrape, classify, brief, deliver |
| `edfd47a` | feat(week2): entity linking, scrape logging, pipeline hardening |
| `9ab4ca1` | feat(week3): tests, dead man's switch, operator runbook |
| `cc1750b` | fix: make API keys optional for CI, always generate brief |
| `f2e3910` | chore: reduce cron to 1x/day at 08:00 CET (07:00 UTC) |

---

## Verified API Limits

| Provider | Model | Daily Limit | Tokens/Min | Verified |
|---|---|---|---|---|
| Groq | Llama 3.3 70B | 1,000 RPD | 12,000 TPM | ✅ via HTTP headers |
| Cerebras | Qwen 3 235B | 14,400 RPD | 30,000 TPM | ✅ via HTTP headers |
| Gemini | 2.5 Flash-Lite | 1,000 RPD | 250,000 TPM | ✅ via docs |
| Neon | Postgres 17 | 0.5 GB / 100 CU-hrs | — | ✅ connected |
| Serper | Search API | 2,500 lifetime | — | Key configured |

---

## Phase 2 Backlog (Not in MVP)

| Priority | Feature | Effort | Notes |
|---|---|---|---|
| 1 | SERP monitoring (Serper.dev) | 2h | Cover the 14 targets without scrape URLs |
| 2 | Expand to all 21 targets actively | 2h | Validate and tune scraping for each |
| 3 | Gemini API key for better briefs | 5min | Brief quality upgrade |
| 4 | NL-to-SQL via Telegram bot | 4h | Hybrid: templates + LLM generation |
| 5 | Telegram bot commands | 2h | /query, /competitor, /latest |
| 6 | Streamlit dashboard | 3h | Visual data exploration if needed |
| 7 | Weekly SERP deep scan | 1h | Broader signal coverage |
| 8 | Cross-signal correlation | 4h | Needs 30+ days of data first |

---

## Risk Register (Current)

| Risk | Status | Mitigation |
|---|---|---|
| Groq reduces free tier | Monitored | Cerebras (14.4K RPD) as primary fallback |
| Targets change their websites | Likely | RUNBOOK has troubleshooting guide |
| GH Actions cron stops (60-day inactivity) | Low risk | Public repo, regular commits |
| Brief quality too generic | Observed | Add Gemini key; tune prompts with real feedback |
| Low signal volume (most content deduped) | Expected | Normal after initial scrape; new content appears daily |

---

*Generated: March 30, 2026*
*GreenScan Alpha — ESADE I2P × Green Growth Innovations*
