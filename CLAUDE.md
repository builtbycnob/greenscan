# GreenScan

Dual-layer market intelligence pipeline for Green Growth Innovations (precision ag startup).
Monitors 120 targets: 67 potential customers + 53 competitors. Classifies signals,
discovers contacts, generates daily Battlefield Brief with Opportunity Radar +
Competitive Intelligence sections. Budget: €0/month (all free tiers).

## Stack
- **Pipeline:** Python 3.12+, uv, asyncpg, Crawl4AI (Playwright), newspaper4k, feedparser
- **LLM Primary:** Groq (Llama 3.3 70B, 1000 RPD, 12K TPM)
- **LLM Fallback:** Cerebras (Qwen 3 235B, 14400 RPD, 1M TPD)
- **LLM Brief:** Gemini 2.5 Flash (250 RPD) or Groq fallback
- **LLM Classify Fallback:** Gemini 2.5 Flash Lite (3rd tier after Groq → Cerebras)
- **Database:** Neon Postgres 17 (0.5GB, pg_trgm, scale-to-zero, aws-us-east-1)
- **Delivery:** Telegram Bot API, multi-recipient (comma-separated TELEGRAM_CHAT_ID)
- **Scheduling:** GitHub Actions cron (04:00 UTC daily = 06:00 CEST)
- **SERP:** Serper.dev (2,500 lifetime credits) for contact LinkedIn lookups

## Commands
- `uv run ruff check --fix && uv run ruff format` — lint Python
- `uv run python -m pytest -x` — test pipeline (51 tests)
- `uv run python -m pytest -x -m integration` — test with real API calls
- `uv run python -m pipeline demo` — scrape + RSS + classify + brief (stdout)
- `uv run python -m pipeline daily` — full pipeline with DB + contacts + Telegram
- `uv run python scripts/parse_csv_targets.py` — regenerate targets from CSVs
- `uv run python scripts/discover_urls.py --dry-run` — discover URLs for pending targets

## Architecture
- `pipeline/scraper/` — web.py (Crawl4AI), rss.py (feedparser), serp.py (Serper.dev), registry.py (YAML)
- `pipeline/classifier/` — llm.py (3-tier fallback), categorizer.py, prompts.py (dual-type)
- `pipeline/enrichment/` — dedup.py (SHA256), contacts.py (LinkedIn via SERP), linker.py (pg_trgm)
- `pipeline/storage/` — db.py (asyncpg), migrations/001_initial.sql
- `pipeline/brief/` — generator.py (dual-section: Opportunity Radar + Competitive Intelligence)
- `pipeline/delivery/` — telegram.py (httpx raw, telegramify-markdown, multi-recipient)
- `pipeline/main.py` — orchestrator (demo + daily modes, RSS + web + contacts)
- `targets.yaml` — 120 targets (67 customers + 53 competitors) with extended metadata
- `scripts/` — one-time migration scripts (CSV parser, URL discovery)

## Key Constraints
- IMPORTANT: Groq free tier = 1000 RPD, 100K TPD. Drain-and-switch: use each provider to 90% then next. Batch 10 signals per request.
- IMPORTANT: Cache Playwright browsers in GitHub Actions — uncached runs burn 2x CI minutes
- IMPORTANT: Serper = 2,500 lifetime credits. Contact lookups capped at 20/day. No SERP monitoring yet.
- Dedup via SHA256 content_hash (UNIQUE constraint on signals table, cross-run via DB)
- All LLM prompts in English
- Monitoring: BOTH customers AND competitors. Dual scoring rubrics per type.
- IMPORTANT: Signals must be EVENT-DRIVEN (something happened). Static page descriptions get score 0.
- Classifier score 0-5: customer (sales opportunity) vs competitor (threat level)
- Brief caps competitor signals at 5 to prevent noise domination
- Contact discovery: signal_mention (named people) or 🔍 company_lookup (generic C-level)
- No contact lookup for competitors (Serper budget savings)

## Database
- 6 tables: targets, companies, contacts, signals, briefs, scrape_logs
- Schema in pipeline/storage/migrations/001_initial.sql
- Fuzzy search via pg_trgm on companies.name and contacts.full_name
- Neon pooled connection string (PgBouncer built-in)
