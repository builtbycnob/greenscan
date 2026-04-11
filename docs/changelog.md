# GreenScan — Complete Changelog

22 commits | 2026-03-29 → 2026-04-10 | All on `main` branch

---

## 1. `eb19352` — 2026-03-29 — MVP Pipeline

**feat: MVP pipeline — scrape, classify, brief, deliver**

The foundational commit. Built the entire E2E pipeline from scratch after a deep research phase (8 parallel agents, 12 research docs).

- Crawl4AI web scraper with stealth mode + PruningContentFilter
- 3-tier LLM fallback: Groq (Llama 3.3 70B) → Cerebras (Qwen 3 235B) → Gemini 2.5 Flash-Lite
- 9 opportunity-focused signal categories for Green Growth's ICP
- SHA256 content-hash dedup with cross-run persistence via Neon Postgres
- Battlefield Brief generator (Groq primary, Gemini when key available)
- Telegram delivery via httpx + telegramify-markdown
- 21 target companies in targets.yaml (from founder's ICP spreadsheet)
- 15 unit + 3 integration tests
- GitHub Actions workflows (daily cron + CI)
- Neon Postgres schema: 6 tables with pg_trgm and GIN indexes

**Impact:** Project goes from zero to working pipeline in one commit.

---

## 2. `edfd47a` — 2026-03-29 — Entity Linking & Scrape Logging

**feat(week2): entity linking, scrape logging, pipeline hardening**

Intelligence layer: connecting raw signals to known companies/contacts in the DB.

- Entity linker: pg_trgm fuzzy match to companies/contacts tables
- Scrape logging: every run logged with run_id, counts, duration to `scrape_logs` table
- Pipeline failure handling: logs to DB + Telegram alert on failure
- Cross-run dedup verified (8 hashes loaded, 7/7 duplicates filtered)
- CI workflow for unit tests on push

---

## 3. `9ab4ca1` — 2026-03-29 — Tests, Dead Man's Switch, Runbook

**feat(week3): tests, dead man's switch, operator runbook**

Hardening pass: testing, monitoring, operator documentation.

- 18 unit tests (dedup, models, registry, brief, fallback, circuit breaker)
- 6 integration tests (classifier, storage, linker, fallback chain)
- Dead man's switch: GH Actions workflow alerts if no brief by morning
- RUNBOOK.md: add targets, debug failures, rotate secrets, monitoring queries
- Fixed `datetime.utcnow()` deprecation warnings

---

## 4. `cc1750b` — 2026-03-30 — CI Fix & Brief Threshold

**fix: make API keys optional for CI, always generate brief**

First CI fix — tests were failing because Settings required API keys at import time.

- API keys default to `""` (validated at call time, not import)
- Brief threshold: `min_score=1` for daily runs (always send a brief if signals exist)
- Score >= 3 was too restrictive and produced empty briefs

---

## 5. `f2e3910` — 2026-03-30 — Reduce Cron Frequency

**chore: reduce cron to 1x/day at 08:00 CET (07:00 UTC)**

3x/day was overkill for the signal volume. Saves CI minutes and API quota.

---

## 6. `369017f` — 2026-03-30 — Sprint Review & Backlog

**docs: add sprint review and product backlog**

SPRINT_REVIEW.md (historical snapshot of Sprint 1-2) and BACKLOG.md (prioritized product backlog with 14 stories across 5 priorities).

---

## 7. `a6ee1ce` — 2026-04-01 — Brief Formatting per Founder Feedback

**feat: brief format per founder feedback — links, people, drop generic advice**

First round of founder feedback. Shifted from generic strategy advice to concrete intelligence.

- Brief now includes source URLs, company websites, named people with roles
- Removed "Key Takeaways" and "Suggested Actions" sections (founder: "drop generic actions")
- Added "People to Watch" section for decision-makers
- Classifier prompt updated to extract people with titles
- Batch prompt includes signal URL for source linking

**Founder request:** "add links (website, linkedin, news), people responsible, drop generic actions/takeaways, focus on news topic and links"

---

## 8. `c3d9c5b` — 2026-04-08 — Target Expansion to 124

**feat: expand targets to 124 (67 customers + 57 competitors)**

Major scope expansion: from monitoring 21 customers to 124 targets (dual-layer intelligence).

- CSV parser script: reads 4 founder CSVs (EU/US customers + competitors), deduplicates overlaps
- Extended Target model: `type`, `region`, `threat_level`, `contact_lookup`, `decision_maker_titles`, `competitor_type`, `overlap`, `core_product`, `hq`, `crop_focus`, `why_icp`
- New helpers: `get_rss_targets()`, `get_customer_targets()`, `get_competitor_targets()`
- targets.yaml: 21 → 124 entries with rich metadata

---

## 9. `b69427f` — 2026-04-08 — URL & RSS Discovery

**feat: URL & RSS discovery for 124 targets**

Automated discovery of newsroom URLs and RSS feeds for all new targets.

- Discovery script: probes 16 common newsroom paths + 10 RSS paths per target
- Checks HTML for `<link rel="alternate">` RSS tags
- Results: 65 scrape URLs, 26 RSS feeds discovered
- 68 targets with active monitoring, 55 remain serp-only

---

## 10. `a179f3b` — 2026-04-08 — Dual Intelligence Pipeline

**feat: dual intelligence pipeline (customer + competitor)**

Core pipeline refactored to handle both target types with separate scoring.

- RSS scraping activated alongside web scraping in daily pipeline
- Separate CUSTOMER and COMPETITOR scoring rubrics in classifier prompts
- 2 new categories: `product_launch`, `market_move` (total: 11)
- Brief restructured: Opportunity Radar + Competitive Intelligence sections
- Competitor signals capped at 5 in brief (noise prevention)
- Per-type score thresholds: customer min=1, competitor min=3
- `target_type` flows through entire classify → brief chain

---

## 11. `410762b` — 2026-04-08 — Contact Discovery via Serper

**feat: contact discovery for customer signals via Serper**

LinkedIn contact lookup for decision-makers mentioned in customer signals.

- Serper.dev client (`pipeline/scraper/serp.py`): SERP queries, LinkedIn result parsing
- Contact enrichment (`pipeline/enrichment/contacts.py`): two modes:
  - `signal_mention`: named people in signal → SERP LinkedIn lookup
  - `company_lookup` (tagged with search icon): generic C-level search using `decision_maker_titles` from YAML
- Integrated between classification and brief generation
- Budget guard: configurable daily cap (default 20 Serper lookups)
- 11 new tests (5 serp + 6 contacts)

---

## 12. `356ec4e` — 2026-04-08 — Documentation Update

**docs: update CLAUDE.md and BACKLOG.md for target expansion**

Aligned documentation with the expanded pipeline. Deprecated `greenscanalpha/` (design-only prototype). Archived founder CSVs to `data/csv_import/`.

---

## 13. `7209db2` — 2026-04-08 — Major Target Expansion (squash)

**feat: major target expansion — 124 dual-layer intelligence pipeline**

Integration commit combining the target expansion (commits 8-12) into a coherent description. 47 tests, all passing.

---

## 14. `9c26d86` — 2026-04-08 — Cron Time Optimization

**chore: move cron to 04:00 UTC to avoid GH Actions delay**

GH Actions free tier delayed 2-3 hours at the 07:00 UTC slot (peak Europe). Moved to 04:00 UTC (06:00 CEST), off-peak. Brief now arrives ~06:30 CEST instead of ~12:00.

- Dead man's switch shifted to 05:00 UTC (1 hour after pipeline)

---

## 15. `fe7bdce` — 2026-04-08 — Doc Sync

**docs: sync project docs with codebase state**

Fixed stale claims: cron time (07:00→04:00 UTC), target counts (65→66 web, 26→28 RSS), marked RSS tech debt as fixed, added gemini-2.5-flash-lite to CLAUDE.md.

---

## 16. `68c4fa1` — 2026-04-08 — Changelog

**docs: add complete changelog through 2026-04-08**

First version of this changelog file (`docs/changelog_2026-04-08.md`).

---

## 17. `8ff627e` — 2026-04-08 — Deep URL Discovery

**feat: deep URL discovery — 106/120 targets now actively monitored**

Manual web research + deep discovery script resolved 42 of 55 serp-only targets.

- Removed 4 defunct companies (Gro Intelligence, PrecisionHawk, SST Software, AGCO duplicate)
- Renamed 5 targets for acquired companies (Gavilon→Viterra, Descartes→EarthDaily, Hummingbird→Agreena, Toepfer→ADM Europe, Unifarm→De Heus)
- Fixed wrong URLs (unifarm.nl was Wageningen University, not De Heus)
- Target count: 124 → 120 (67 customers + 53 competitors)
- Only 13 targets remain serp-only (mostly small farms without newsrooms)

---

## 18. `2680f1e` — 2026-04-09 — Drain-and-Switch Quota Management

**fix(classifier): drain-and-switch quota management with dual RPD+TPD tracking**

Major quota management overhaul. The old circuit breaker approach (5 failures before switching, RPD-only tracking) failed when Groq's TPD was exhausted before RPD threshold.

- Proactive: check both request AND token rate limit headers, switch at 90%
- Reactive: immediate switch on first 429 (no 5-failure delay)
- Batch size 5→10, content truncation 1500→800 chars (~50% token savings)
- Replaced `SimpleCircuitBreaker` with drain-and-switch pattern

---

## 19. `a333f71` — 2026-04-09 — CI Re-raise Fix

**fix(pipeline): re-raise exceptions so CI reports actual failures**

`run_daily()` was swallowing exceptions after logging + Telegram alert, causing GitHub Actions to report success on pipeline failures. Also: brief generator falls back to Groq on Gemini 503 errors.

---

## 20. `9c08cf7` — 2026-04-09 — Content Truncation Bump

**fix(classifier): bump content truncation to 1000 chars**

800 chars (from commit 18) was too aggressive — 20% of signals have useful info in the 800-1500 range. 1000 covers the relevant content window while saving ~33% tokens vs the original 1500.

---

## 21. `415755f` — 2026-04-10 — Formatting

**style: ruff format test_brief.py**

Auto-format only, no logic changes.

---

## 22. `66c3ee9` — 2026-04-10 — CLAUDE.md Sync

**docs: sync CLAUDE.md with codebase state**

Updated CLAUDE.md to reflect post-overhaul state: 120 targets (not 124), 49 tests (not 47), batch size 10, 90% drain-and-switch.

---

## 23. `6eacf8f` — 2026-04-11 — Contact Rekey + Dead Parameter Removal

**fix(brief): rekey contacts by content_hash, remove dead min_score param**

Contact discovery returned `dict[int, list]` keyed by position in the unfiltered signal list. Brief generator applied this against the filtered list — wrong contacts mapped to wrong signals after low-score filtering.

- Rekeyed contacts by `content_hash` (stable across any filter/reorder)
- `discover_contacts` accepts `signal_keys` param, returns `dict[str, list]`
- `generator.py` looks up by `filtered_raw[i].content_hash`
- Removed unused `min_score` parameter from `generate_brief` (accepted but never used in filtering logic)
- Added test for contact survival after score filtering

---

## 24. `5887faa` — 2026-04-11 — Dead Man's Switch Freshness

**fix(ops): dead man's switch checks brief freshness by date**

Old check: `if brief is None` — yesterday's brief passed, so a failed pipeline triggered no alert.

- Added `get_todays_brief()`: checks `generated_at::date = CURRENT_DATE`
- Added `pipeline_ran_today()`: checks `scrape_logs.started_at::date = CURRENT_DATE`
- Workflow: if pipeline didn't run → alert. If ran but no brief + signals exist → alert. If ran + no signals (all dedup) → OK.

---

## 25. `b67187a` — 2026-04-11 — Brief Score Threshold

**fix(brief): bump brief_min_score_customer from 1 to 2**

Score 1 = "noise" per the classifier rubric (e.g., "sponsors golf tournament"). These were leaking into the Battlefield Brief. Setting min threshold to 2 ("low relevance") ensures only actionable signals reach the founder.

---

## 26. `fb3a1d3` — 2026-04-11 — Keep-Alive Workflow

**feat(ops): add monthly keep-alive workflow for GH Actions cron**

GitHub disables scheduled workflows after 60 days of repo inactivity (no pushes to default branch). This silently kills both the daily pipeline AND the dead man's switch. Monthly cron pushes a timestamp to `.github/.keepalive`. Self-contained, zero third-party actions.

---

## 27. `52f1245` — 2026-04-11 — Neon Timeouts + Tech Debt

**fix(storage): add connect/command timeouts, fix utcnow and f-string SQL**

- `timeout=30` and `command_timeout=30` on `asyncpg.create_pool` — prevents indefinite hangs on Neon cold starts (scale-to-zero)
- `datetime.utcnow()` → `datetime.now(UTC)` (deprecation fix)
- f-string SQL interpolation → parameterized `make_interval(days => $1)`

---

## 28. `d046dbc` — 2026-04-11 — Batch Insert

**perf(storage): single-connection batch insert with status counting**

Old: `insert_signals_batch` called `insert_signal` N times, each acquiring and releasing a pool connection. With 60+ signals on Neon's serverless latency, this was the storage bottleneck.

- Single `pool.acquire()`, loop `conn.execute()` on one connection
- Parse asyncpg status string (`INSERT 0 1` vs `INSERT 0 0`) for accurate dedup counting
- SQL extracted to class constant `_INSERT_SQL` shared by both methods

---

## 29. `2dc2421` — 2026-04-11 — Failure Rate Logging

**fix(scraper): log aggregate failure rates for web and RSS scrapers**

- Web scraper: `failed`/`skipped` counters, summary log: `"Web scrape: 85/172 success, 30 failed, 57 skipped"`
- RSS: logs article extraction failures per feed with count
- `_extract_article` was swallowing all exceptions silently — now logs at `debug` level

---

## Summary

| Metric | Value |
|--------|-------|
| Total commits | 29 |
| Date range | 2026-03-29 → 2026-04-11 |
| Features | 12 |
| Fixes | 10 |
| Perf | 1 |
| Docs | 4 |
| Chores/style | 2 |
| Tests | 51 (37 unit + 14 integration) |
| Targets | 120 (67 customers + 53 competitors) |
| Active monitoring | 107 targets (scrape + RSS) |
| Pipeline stages | scrape (web+RSS) → dedup → classify → link → contacts → store → brief → deliver |
