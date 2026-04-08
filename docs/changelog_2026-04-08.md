# GreenScan — Changelog (as of 2026-04-08)

Complete commit history with descriptions.

---

## 1. `eb19352` — 2026-03-29 — MVP Pipeline

**feat: MVP pipeline — scrape, classify, brief, deliver**

Full E2E pipeline for market intelligence. This is the initial commit that established the entire project.

**What changed:**
- Crawl4AI web scraper with stealth mode + PruningContentFilter
- 3-tier LLM fallback chain: Groq (1K RPD) → Cerebras (14.4K RPD) → Gemini
- 9 opportunity-focused signal categories for Green Growth's ICP
- SHA256 content-hash dedup with cross-run persistence via Neon Postgres
- Battlefield Brief generator (Gemini primary, Groq fallback)
- Telegram delivery via httpx + telegramify-markdown
- 21 target companies defined in targets.yaml
- 15 unit tests + 3 integration tests
- GitHub Actions workflows (daily cron + CI)
- Neon Postgres schema: 6 tables with pg_trgm and GIN indexes

**Files:** 43 added | +9,020 lines

---

## 2. `edfd47a` — 2026-03-29 — Entity Linking & Scrape Logging

**feat(week2): entity linking, scrape logging, pipeline hardening**

Added intelligence layer for connecting signals to known companies/contacts, plus operational logging.

**What changed:**
- Entity linker: pg_trgm fuzzy match to companies/contacts tables
- Scrape logging: every run logged with run_id, counts, duration
- Pipeline failure handling: logs to DB + Telegram alert on failure
- Cross-run dedup verified working (8 hashes, 7/7 filtered correctly)
- CI workflow for unit tests on push

**Files:** 3 modified | +220 lines

---

## 3. `9ab4ca1` — 2026-03-29 — Tests, Dead Man's Switch, Runbook

**feat(week3): tests, dead man's switch, operator runbook**

Hardened the pipeline with comprehensive testing, monitoring, and operator documentation.

**What changed:**
- 18 unit tests (dedup, models, registry, brief, fallback, circuit breaker)
- 6 integration tests (classifier, storage, linker, fallback chain)
- Dead man's switch: GitHub Actions workflow alerts if no brief generated
- RUNBOOK.md: how to add targets, debug failures, rotate secrets, monitoring queries

**Files:** 7 modified/added | +484 lines

---

## 4. `cc1750b` — 2026-03-30 — CI Fix & Brief Threshold

**fix: make API keys optional for CI, always generate brief**

Fixed test failures in CI caused by missing API secrets, and lowered the brief threshold.

**What changed:**
- Settings: API keys default to "" (validated at call time, not import time)
- Brief threshold: min_score=1 for daily runs (always send a brief if signals exist)
- Fixed CI test failures caused by missing secrets in test environment

**Files:** 3 modified | +34/-5 lines

---

## 5. `f2e3910` — 2026-03-30 — Reduce Cron Frequency

**chore: reduce cron to 1x/day at 08:00 CET (07:00 UTC)**

Reduced from 3x/day to 1x/day to save CI minutes and API quota.

**Files:** 1 modified | +1/-1 lines

---

## 6. `369017f` — 2026-03-30 — Sprint Review & Backlog

**docs: add sprint review and product backlog**

Added comprehensive sprint review document and a prioritized product backlog with 14 stories across 5 priorities.

**Files:** 2 added | +567 lines

---

## 7. `a6ee1ce` — 2026-04-01 — Brief Formatting per Founder Feedback

**feat: brief format per founder feedback — links, people, drop generic advice**

First founder feedback iteration. Shifted from generic strategy advice to concrete, actionable intelligence.

**What changed:**
- Brief now includes source URLs, company websites, named people with roles
- Removed "Key Takeaways" and "Suggested Actions" sections
- Added "People to Watch" section for decision-makers and potential champions
- Classifier prompt updated to extract people with titles
- Batch prompt now includes signal URL for source linking

**Founder request:** *"add links (website, linkedin, news), people responsible, drop generic actions/takeaways, focus on news topic and links"*

**Files:** 4 modified | +38/-14 lines

---

## 8. `c3d9c5b` — 2026-04-08 — Target Expansion to 124

**feat: expand targets to 124 (67 customers + 57 competitors)**

Major expansion: parsed founder's March 2026 CSV export with EU + US companies.

**What changed:**
- CSV parser script (`scripts/parse_csv_targets.py`): reads 4 CSVs, deduplicates EU/US overlaps, merges with existing verified URLs
- Extended Target Pydantic model: added `type` (customer/competitor), `region`, `threat_level`, `contact_lookup`, `decision_maker_titles`, `competitor_type`, `overlap`, `core_product`, `hq`, `crop_focus`, `why_icp`
- New helpers: `get_rss_targets()`, `get_customer_targets()`, `get_competitor_targets()`
- Added `LOW` priority and `PENDING_DISCOVERY` monitoring type
- targets.yaml: from 21 entries to 124 (67 customers + 57 competitors)
- Updated registry tests for new model and counts

**Files:** 4 modified/added | +2,853/-226 lines

---

## 9. `b69427f` — 2026-04-08 — URL & RSS Discovery

**feat: URL & RSS discovery for 124 targets**

Automated discovery of newsroom URLs and RSS feeds across all 124 targets.

**What changed:**
- Discovery script (`scripts/discover_urls.py`): probes 16 common newsroom paths + 10 RSS paths per target, checks HTML for `<link rel="alternate">` RSS tags
- Results: 65 targets with scrape URLs, 26 with RSS feeds discovered
- 68 targets now have active monitoring (direct_scrape, rss, or both)
- 55 targets remain serp-only (no scrapeable URL or RSS found)
- targets.yaml updated with all discovered URLs and monitoring types

**Files:** 2 modified/added | +691/-189 lines

---

## 10. `a179f3b` — 2026-04-08 — Dual Intelligence Pipeline

**feat: dual intelligence pipeline (customer + competitor)**

Core pipeline adaptation to handle both target types with separate scoring rubrics.

**What changed:**
- RSS scraping activated in daily pipeline alongside web scraping
- Classifier prompts updated with separate CUSTOMER and COMPETITOR scoring rubrics
- Added 2 new categories: `product_launch` and `market_move` (total: 11)
- Brief restructured into 2 sections: Opportunity Radar + Competitive Intelligence
- Competitor signals capped at 5 in brief (configurable) to prevent noise domination
- Per-type score thresholds: customer min=1, competitor min=3
- `target_type` passed through entire classify → brief chain for context
- New config settings: `competitor_signals_cap`, `brief_min_score_customer`, `brief_min_score_competitor`, `contact_min_score`
- Updated tests for dual-section brief and competitor cap

**Files:** 6 modified | +264/-71 lines

---

## 11. `410762b` — 2026-04-08 — Contact Discovery via Serper

**feat: contact discovery for customer signals via Serper**

LinkedIn contact lookup for decision-makers mentioned in customer signals.

**What changed:**
- Serper.dev client (`pipeline/scraper/serp.py`): SERP queries, LinkedIn result parsing
- Contact enrichment module (`pipeline/enrichment/contacts.py`): two modes:
  - `signal_mention`: named people in signal → SERP LinkedIn lookup
  - `company_lookup` (🔍 tagged): generic C-level search using decision_maker_titles from YAML
- Integrated into daily pipeline between classification and brief generation
- Contacts appear in brief as "Key Contacts" in People to Watch section
- Budget guard: configurable daily cap (default 20 Serper lookups)
- 5 tests for serp parsing, 6 tests for contact discovery logic

**Files:** 6 added/modified | +499 lines

---

## 12. `356ec4e` — 2026-04-08 — Documentation Update

**docs: update CLAUDE.md and BACKLOG.md for target expansion**

Aligned all documentation with the expanded pipeline.

**What changed:**
- CLAUDE.md: updated to 124 targets, dual intelligence, contact discovery, serp.py
- BACKLOG.md: updated capabilities table, marked contact discovery (3.3) as done, added 4 decision log entries
- Deprecated `greenscanalpha/` directory (was design-only prototype, no code)
- Archived founder CSVs to `data/csv_import/`
- Added `data/` to `.gitignore`

**Files:** 5 modified | +107/-51 lines

---

## 13. `9c26d86` — 2026-04-08 — Cron Time Optimization

**chore: move cron to 04:00 UTC to avoid GH Actions delay**

Addressed 2-3 hour cron delays by moving to off-peak slot.

**What changed:**
- Daily pipeline: 07:00 UTC → 04:00 UTC (06:00 CEST)
- Dead man's switch: 07:00 UTC → 05:00 UTC (1 hour after pipeline)
- Expected improvement: brief delivery ~06:30 CEST instead of ~12:00 CEST

**Files:** 2 modified | +2/-2 lines

---

## 14. `fe7bdce` — 2026-04-08 — Doc Sync

**docs: sync project docs with codebase state**

Fixed stale claims found by automated sync-project verification.

**What changed:**
- CLAUDE.md: fixed cron time (07:00→04:00 UTC), added gemini-2.5-flash-lite mention
- BACKLOG.md: fixed cron times, target counts (65→66 web, 26→28 RSS), marked RSS tech debt as fixed

**Files:** 2 modified | +8/-7 lines

---

## Summary

| Metric | Value |
|--------|-------|
| Total commits | 15 (including merge) |
| Date range | 2026-03-29 → 2026-04-08 |
| Total lines added | ~14,500 |
| Test count | 47 (35 unit + 12 integration) |
| Target companies | 124 (67 customers + 57 competitors) |
| Active monitoring | 68 targets (scrape + RSS) |
| Pipeline features | Web scrape, RSS, dedup, classify (dual), entity linking, contact discovery, brief (dual-section), Telegram delivery |
