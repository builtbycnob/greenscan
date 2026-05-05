# GreenScan — Project Overview

## What is GreenScan?

GreenScan is an automated market intelligence pipeline built for **Green Growth Innovations**, a precision agriculture startup based in Barcelona. Green Growth makes retrofit yield monitors for combines and potato harvesters — hardware that clips onto existing farm equipment to measure crop yield in real-time.

The pipeline monitors **120 target companies** (67 potential customers + 53 competitors) across the EU and US agriculture sector. Every morning at 06:00 CEST, it delivers a **Battlefield Brief** to the founder's Telegram with two sections:

- **Opportunity Radar** — sales signals from potential customers (expansions, tech investments, leadership changes, vendor searches)
- **Competitive Intelligence** — threat signals from competitors (product launches, funding rounds, market moves)

The entire system runs on free tiers. Budget: **zero euros per month**.

---

## How It Works

The pipeline runs daily on GitHub Actions and follows 9 stages:

```
1. SCRAPE      Web (Crawl4AI) + RSS (feedparser) → raw content from 107 target websites
2. DEDUP       SHA256 content hash → skip signals already seen in previous runs (via Neon DB)
3. PRE-FILTER  Event-verb dictionary + min length → drop static/non-event content before LLM
4. CLASSIFY    3-tier LLM (Groq → Cerebras → Gemini) with retry-on-5xx → category, score 0-5, summary, people
5. LINK        pg_trgm fuzzy match → connect signals to known companies/contacts in DB
6. CONTACTS    Serper.dev LinkedIn lookup → find decision-makers for customer signals
7. STORE       Insert new signals + contacts into Neon Postgres
8. BRIEF       Gemini 2.5 Flash (or Groq fallback) with retry → generate dual-section Battlefield Brief
9. DELIVER     Telegram Bot API → chunked + escaped → send to founder + dev
```

### Signal Classification

Each scraped signal gets classified into one of 11 categories:
- `precision_ag_adoption`, `sustainability_initiative`, `tech_investment`, `vendor_search`, `expansion`, `leadership_change`, `partnership`, `funding_m_and_a`, `product_launch`, `market_move`, `other`

Scoring uses dual rubrics:
- **Customer signals** (0-5): How strong is this as a sales opportunity for Green Growth?
- **Competitor signals** (0-5): How threatening is this to Green Growth's market position?

Only event-driven signals get scored. Static page descriptions (e.g., "About Us") get score 0 and are filtered out.

### LLM Quota Management

Free-tier LLM providers have strict rate limits. GreenScan uses a **drain-and-switch** strategy:

1. **Groq** (primary) — `llama-3.3-70b-versatile`, 1,000 RPD, 100K TPD, **12K TPM** (TPM is the binding limit — Groq drains in 2-3 batches)
2. **Cerebras** (fallback 1) — `gpt-oss-120b`, 14,400 RPD / 1M TPD nominal, with reduced RPM on "high demand" models — we throttle to ≤10 RPM via 6-second inter-call sleep
3. **Gemini** (fallback 2 + brief) — `gemini-2.5-flash-lite` (classify), `gemini-2.5-flash` (brief), 250 RPD

Each provider is used until 90% of its quota (checking both RPD and TPD via HTTP headers), then switches to the next. On a 429 rate limit error, switches immediately. **Transient 5xx errors are retried up to 3 times** with exponential backoff (1s/2s/4s) before falling through.

Signals are batched 10 per request and content is truncated to 1,000 chars to minimize token consumption. The pre-filter (added May 2026) drops ~50% of signals before they reach the classifier.

### Contact Discovery

For customer signals with score >= 3, GreenScan looks up decision-makers:

- **signal_mention**: If the signal names specific people, search LinkedIn via Serper.dev
- **company_lookup**: If no people named, search for C-level roles defined in `targets.yaml` (e.g., "VP Grain Origination", "Director Digital Farming")

Budget: 20 Serper lookups per day (2,500 lifetime credits). No contact lookup for competitors.

---

## Architecture

```
greenscan/
├── pipeline/
│   ├── scraper/          web.py, rss.py, serp.py, registry.py, models.py
│   ├── classifier/       llm.py (3-tier + retry-on-5xx + Cerebras throttle),
│   │                     prefilter.py (event-verb filter, May 2026),
│   │                     categorizer.py, prompts.py
│   ├── enrichment/       dedup.py, contacts.py, linker.py
│   ├── storage/          db.py (asyncpg), migrations/001_initial.sql
│   ├── brief/            generator.py (dual-section, retry-on-5xx)
│   ├── delivery/         telegram.py (multi-recipient, chunker ≤3500)
│   ├── config.py         Pydantic settings (env-based)
│   └── main.py           Orchestrator (demo + daily modes)
├── tests/                62 tests (51 unit + 11 integration)
├── scripts/              CSV parser, URL discovery, deep discovery
├── targets.yaml          120 targets with rich metadata
├── .github/workflows/    4 workflows (daily, CI, dead man's switch, keep-alive)
├── docs/                 Research docs, changelog, overview, handover
├── CLAUDE.md             Project instructions
├── BACKLOG.md            Product backlog & roadmap
└── RUNBOOK.md            Operator handbook
```

### Database (Neon Postgres 17)

6 tables: `targets`, `companies`, `contacts`, `signals`, `briefs`, `scrape_logs`

- `pg_trgm` extension for fuzzy name matching
- GIN indexes on JSONB columns for entity search
- SHA256 `content_hash` UNIQUE constraint for cross-run dedup
- Pooled connection via PgBouncer (Neon built-in)
- Scale-to-zero on AWS us-east-1 (free tier: 0.5GB, 100 compute-hours/month)

### Scheduling

- **Daily pipeline**: GitHub Actions cron at 04:00 UTC (06:00 CEST, off-peak slot)
- **Dead man's switch**: Separate workflow at 05:00 UTC, alerts on Telegram if no brief
- **CI**: Lint (ruff) + unit tests on every push

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Language | Python 3.12 | Async ecosystem, LLM SDKs |
| Package manager | uv | Fast, deterministic |
| Web scraping | Crawl4AI 0.8.6 | Playwright-based, stealth mode, batch crawling |
| RSS parsing | feedparser + newspaper4k | Standard + full article extraction |
| LLM (classify) | Groq `llama-3.3-70b-versatile` → Cerebras `gpt-oss-120b` → Gemini `flash-lite` | Free tiers, drain-and-switch + retry-on-5xx |
| LLM (briefs) | Gemini 2.5 Flash → Groq fallback | Long context, narrative quality |
| Database | Neon Postgres 17 | Free, serverless, pg_trgm |
| Delivery | Telegram Bot API (httpx) | Founder's preference, zero cost |
| SERP | Serper.dev | LinkedIn contact lookup |
| CI/CD | GitHub Actions | Free for public repos |
| Linting | ruff | Fast, replaces flake8+black+isort |
| Validation | Pydantic + pydantic-settings | Type safety, env parsing |
| Retry | tenacity (general) + custom `_retry_on_5xx` in `llm.py` | Targeted at httpx 5xx; 429 already handled by drain-and-switch |

---

## Target Coverage

120 targets across 2 types and 2 regions:

| Type | Count | Monitoring |
|------|-------|-----------|
| Customers | 67 | Sales opportunities, contact discovery |
| Competitors | 53 | Threat assessment, no contact lookup |

| Monitoring Mode | Count | Method |
|----------------|-------|--------|
| direct_scrape | 75 | Crawl4AI web scrape |
| direct_scrape_and_rss | 24 | Web + RSS feed |
| rss | 7 | RSS feed only |
| serp_only | 13 | Pending SERP monitoring module |
| sec_ir | 1 | SEC/IR filings (pending) |

Industries covered: grain traders, food processors, farm operators, farmland investors, crop insurance, agri inputs, precision ag competitors, satellite/drone companies, farm management software.

---

## Running the Pipeline

```bash
# Install dependencies
uv sync

# Run demo (3 targets, stdout output)
uv run python -m pipeline demo

# Run full daily pipeline (all targets, DB, Telegram)
uv run python -m pipeline daily

# Lint
uv run ruff check --fix && uv run ruff format

# Test
uv run python -m pytest -x

# Integration tests (requires API keys)
uv run python -m pytest -x -m integration
```

### Environment Variables

Required for daily mode (`.env`):
- `GROQ_API_KEY` — primary LLM provider
- `CEREBRAS_API_KEY` — fallback LLM provider
- `NEON_DATABASE_URL` — Postgres connection string
- `TELEGRAM_BOT_TOKEN` — delivery
- `TELEGRAM_CHAT_ID` — comma-separated recipient IDs

Optional:
- `GEMINI_API_KEY` — better briefs + 3rd tier classifier
- `SERPER_API_KEY` — contact discovery

---

## Project Context

- **Client**: Green Growth Innovations (greengrowth.tech)
- **Product**: Retrofit yield monitors for combines and potato harvesters
- **Founded**: 2021 by Alfiya Kayumova (CEO, Barcelona)
- **Stage**: Pre-seed ($300K)
- **Academic**: ESADE I2P project
- **Founder contact**: Evgeny Savin (@easavin on Telegram)
- **Repository**: github.com/builtbycnob/greenscan (public)
- **Developer**: Corrado (builtbycnob) + Claude AI (pair programming)
- **Timeline**: March 29, 2026 → ongoing (34+ commits as of May 5, 2026)
