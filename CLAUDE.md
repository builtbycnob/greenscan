# GreenScan

Market intelligence pipeline for Green Growth Innovations (precision ag startup).
Monitors 21 target companies (Green Growth's ICP), classifies signals for sales
opportunities, generates daily Battlefield Brief. Budget: €0/month (all free tiers).

## Stack
- **Pipeline:** Python 3.12+, uv, asyncpg, Crawl4AI (Playwright), newspaper4k, feedparser
- **LLM Primary:** Groq (Llama 3.3 70B, 1000 RPD, 12K TPM)
- **LLM Fallback:** Cerebras (Qwen 3 235B, 14400 RPD, 1M TPD)
- **LLM Brief:** Gemini 2.5 Flash (250 RPD) or Groq fallback
- **Database:** Neon Postgres 17 (0.5GB, pg_trgm, scale-to-zero, aws-us-east-1)
- **Delivery:** Telegram Bot API only (no email)
- **Scheduling:** GitHub Actions cron (06:17, 12:17, 18:17 UTC)

## Commands
- `uv run ruff check --fix && uv run ruff format` — lint Python
- `uv run pytest -x` — test pipeline (unit only)
- `uv run pytest -x -m integration` — test with real API calls
- `uv run python -m pipeline demo` — scrape 3 targets + classify + brief (stdout)
- `uv run python -m pipeline daily` — full pipeline with DB persistence + Telegram

## Architecture
- `pipeline/scraper/` — web.py (Crawl4AI), rss.py (feedparser), registry.py (YAML)
- `pipeline/classifier/` — llm.py (3-tier fallback), categorizer.py, prompts.py
- `pipeline/enrichment/` — dedup.py (SHA256 content_hash)
- `pipeline/storage/` — db.py (asyncpg), migrations/001_initial.sql
- `pipeline/brief/` — generator.py (Gemini/Groq)
- `pipeline/delivery/` — telegram.py (httpx raw, telegramify-markdown)
- `pipeline/main.py` — orchestrator (demo + daily modes)
- `targets.yaml` — 21 target companies with URLs, priorities, monitoring types
- `docs/research/` — deep research files (12 files from 8+4 agents)

## Key Constraints
- IMPORTANT: Groq free tier = 1000 RPD. Batch 3-5 signals per request. Route to Cerebras at 80% quota.
- IMPORTANT: Cache Playwright browsers in GitHub Actions — uncached runs burn 2x CI minutes
- Dedup via SHA256 content_hash (UNIQUE constraint on signals table, cross-run via DB)
- All LLM prompts in English
- Neon storage budget: use jsonb_path_ops for compact GIN indexes
- Monitoring approach: target CUSTOMERS (not competitors). Opportunity-focused categories.

## Database
- 6 tables: targets, companies, contacts, signals, briefs, scrape_logs
- Schema in pipeline/storage/migrations/001_initial.sql
- Fuzzy search via pg_trgm on companies.name and contacts.full_name
- Neon pooled connection string (PgBouncer built-in)
