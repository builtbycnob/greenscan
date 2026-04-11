# GreenScan — Product Backlog & Roadmap

**Last updated:** April 11, 2026
**Status:** Dual intelligence live (120 targets), cron 1x/day at 04:00 UTC (06:00 CEST), multi-recipient

---

## Current Capabilities

| Feature | Status | Notes |
|---|---|---|
| Web scraping (100 targets) | ✅ Live | Crawl4AI, stealth mode |
| RSS scraping (33 targets) | ✅ Live | feedparser + newspaper4k |
| Signal classification (11 categories) | ✅ Live | Groq primary, Cerebras fallback, dual rubrics |
| Content deduplication | ✅ Live | SHA256, cross-run via DB |
| Entity linking (pg_trgm) | ✅ Live | Fuzzy match to companies/contacts |
| Dual-section Brief | ✅ Live | Opportunity Radar + Competitive Intelligence |
| Contact discovery (customers) | ✅ Live | Serper LinkedIn lookup, 20/day cap |
| Telegram delivery | ✅ Live | Multi-recipient (dev + founder), daily brief + alerts |
| Database persistence | ✅ Live | Neon Postgres 17, 6 tables |
| GitHub Actions cron | ✅ Live | 04:00 UTC daily (06:00 CEST) |
| Dead man's switch | ✅ Live | Alerts if no brief by 05:00 UTC |
| CI/CD (lint + tests) | ✅ Live | 51 tests |
| 120 targets (67 cust + 53 comp) | ✅ Live | EU + US, extended metadata from founder CSV |

---

## Priority 1 — Quick Wins (1-2 hours each)

These improve the MVP immediately with minimal effort.

### 1.1 Add Gemini API Key for Better Briefs
**Effort:** 5 min | **Impact:** High

The brief generator already supports Gemini 2.5 Flash (1M context window, better narrative quality). Just needs an API key from aistudio.google.com added to `.env` and GitHub Secrets.

### 1.2 ~~Tune Classification Prompts with Real Feedback~~ ✅ DONE (2026-04-06)

Applied founder feedback: added CRITICAL FILTER to reject static page descriptions (score 0). Signals must be event-driven. Relevance scale expanded to 0-5.

### 1.3 Fix Farmland Partners Scraping
**Effort:** 1h | **Impact:** Low

IR page returns too little content (JS-rendered). Options:
- Switch to SEC EDGAR RSS feed for 8-K/10-K filings
- Use Serper to monitor "Farmland Partners news" instead
- Use `wait_until="networkidle"` in Crawl4AI config for this URL

### 1.4 Improve Brief Formatting for Telegram
**Effort:** 1h | **Impact:** Medium

Current briefs can be long and sometimes duplicated by Groq. Improvements:
- Cap brief length to ~500 words for Telegram readability
- Publish full brief to Telegraph (telegra.ph) with Instant View
- Send only TL;DR + link in Telegram message
- Add date header and signal count

### 1.5 Add Quiet Hours for Alerts
**Effort:** 30min | **Impact:** Low

Score-5 critical alerts currently have no time restriction. Add configurable quiet hours (e.g., 22:00-06:00 local) to prevent late-night notifications.

---

## Priority 2 — Signal Coverage Expansion (2-4 hours each)

These increase the volume and quality of signals captured.

### 2.1 SERP Monitoring via Serper.dev
**Effort:** 3h | **Impact:** High

14 of 21 targets have no direct scrape URLs — they're `serp_only`. The Serper API key is already configured. Need to:
- Build `pipeline/scraper/serp.py` using Serper.dev API
- Run SERP queries from `targets.yaml` (1 per target)
- Parse results into `RawSignal` format
- Integrate into daily pipeline
- Budget: ~21 queries/day = ~630/month out of 2,500 lifetime credits

### 2.2 SEC/IR Feed Monitoring
**Effort:** 2h | **Impact:** Medium

3 targets are public companies (Farmland Partners NYSE:FPI, Lamb Weston NYSE:LW, Bayer XETRA:BAYN). Their SEC filings (8-K, 10-K) contain material announcements. Options:
- Parse SEC EDGAR RSS feeds (free, structured)
- Use StockTitan/GlobeNewsWire press release feeds
- Add IR page scraping with JS rendering support

### 2.3 Industry News Sources
**Effort:** 2h | **Impact:** Medium

Add industry-level monitoring beyond individual targets:
- AgFunderNews (agfundernews.com) — AgTech investment news
- Precision Ag (precisionag.com) — precision agriculture technology
- PotatoPro (potatopro.com) — potato industry news
- Future Farming (futurefarming.com) — smart farming
- Capital Press (capitalpress.com) — western US agriculture

These would catch signals about target companies from third-party sources.

### 2.4 ~~Expand to 30+ Targets~~ ✅ DONE (2026-04-08)

Expanded from 21 to 120 targets (67 customers + 53 competitors) across EU + US from founder's March 2026 CSV export. Deep URL discovery resolved 106/120 to active monitoring. Only 13 remain serp-only.

---

## Priority 3 — Intelligence Quality (3-5 hours each)

These make the briefs more useful and actionable.

### 3.1 NL-to-SQL via Telegram Bot
**Effort:** 4h | **Impact:** High

Let the founder ask questions in natural language via Telegram:
- `/query Who adopted precision ag this month?`
- Hybrid approach: 10-15 pre-built query templates + LLM generation for novel questions
- Read-only Postgres role already created
- Security: SELECT-only, LIMIT 100, 5s timeout

### 3.2 Cross-Signal Correlation
**Effort:** 4h | **Impact:** Medium

After 30+ days of data, identify patterns:
- Multiple targets making similar moves (industry trend)
- Temporal clusters (N companies doing X within 7 days)
- Add "Trend & Correlations" section to the brief
- Requires sufficient signal volume to be meaningful

### 3.3 ~~Contact Discovery for Brief Signals~~ ✅ DONE (2026-04-08)

Implemented: Serper LinkedIn lookup for customer signals. Direct match (named people) + company lookup (🔍 tagged). 20/day Serper cap. Phase 2: Hunter.io/Apollo for email.
- Extract person names from scraped content via LLM (NER in classification prompt)
- SERP lookup: `"Name Surname" site:linkedin.com {company}` via Serper (~1 query/contact)
- Add "Key Contacts" section to brief: **name, LinkedIn headline, LinkedIn URL**
- If signal mentions specific people → show those (direct match)
- If no people mentioned → lookup company C-level/procurement via SERP, tag as "🔍 company lookup"
- Store in existing `contacts` table (full_name, title, email, linkedin_url, company_id)
- Sources: scraped page content → Serper LinkedIn lookup → company /about /team pages
- GDPR: only publicly available info, no login-wall scraping
- **Phase 2:** Add Hunter.io (50 free lookups/month) and/or Apollo.io (free tier) for email discovery

### 3.4 Signal Enrichment Pipeline
**Effort:** 3h | **Impact:** Medium

Enrich each signal with additional context:
- Company size/revenue (from Crunchbase/ZoomInfo data)
- Previous interactions with Green Growth (CRM context)
- Related signals from the same company (history view)
- Competitor product comparisons when relevant

### 3.4 Brief Personalization
**Effort:** 2h | **Impact:** Medium

Customize briefs based on what the founder cares about:
- Track which signals the founder clicks/acts on
- Weight future scoring based on demonstrated interest
- Different brief formats for different days (Monday = weekly summary, daily = incremental)

---

## Priority 4 — User Interface (3-8 hours each)

Only build these if Telegram proves insufficient.

### 4.1 Telegram Bot Commands
**Effort:** 3h | **Impact:** Medium

Upgrade from send-only to interactive bot:
- `/latest` — show last 5 signals
- `/competitor Bayer` — signals for a specific target
- `/brief` — regenerate today's brief on demand
- `/stats` — pipeline health (signals/day, dedup rate, API quota)
- Requires upgrading from `httpx` to `python-telegram-bot`

### 4.2 Streamlit Dashboard
**Effort:** 4h | **Impact:** Medium

Lightweight Python dashboard on Streamlit Community Cloud (free):
- Signal feed with filters (date, category, score, target)
- Brief archive viewer
- Pipeline health metrics (scrape_logs visualization)
- Company profile cards
- No JS/TS needed — pure Python

### 4.3 Next.js Web Dashboard
**Effort:** 8h | **Impact:** Low (for 1-3 users)

Full web application — only if the product grows beyond the founder:
- Deploy on Vercel Hobby (confirmed non-commercial use is OK) or Cloudflare Pages
- Next.js 15 with App Router
- shadcn/ui components
- NL-to-SQL chat interface
- Activity heatmap (competitors × time)

---

## Priority 5 — Operational Resilience

### 5.1 ~~GitHub Actions Keep-Alive~~ ✅ DONE (2026-04-11)

Monthly cron pushes timestamp to `.github/.keepalive`, resetting the 60-day inactivity timer. Self-contained, zero third-party actions.

### 5.2 Multi-Channel Delivery
**Effort:** 2h | **Impact:** Low

Add email delivery via Resend (3,000/month free) as backup or archival channel. The module was designed but cut from MVP per founder's preference.

### 5.3 Alert Fatigue Prevention
**Effort:** 1h | **Impact:** Low

As signal volume grows, prevent notification overload:
- Cap score-5 alerts at 3/day
- Batch low-priority signals into weekly digest
- Configurable notification preferences per category

### 5.4 Pipeline Monitoring Dashboard
**Effort:** 2h | **Impact:** Low

Expose pipeline health via a simple API or Telegram command:
- Last N runs with status, duration, signal counts
- API quota consumption across providers
- DB storage usage
- Dedup rate trends

---

## Priority 6 — Cron Reliability

### 6.1 Fix GitHub Actions Cron Delay (2-3h average)
**Effort:** 30min | **Impact:** High

GH Actions cron free tier delays 2-3.5 hours on the `07:00 UTC` slot (peak Europe). Brief arrives 11:00-12:45 CEST instead of ~07:30.
Options (pick one):
- Move cron to `05:00 UTC` (off-peak) — expected delay ~30-60 min, brief ~07:30 CEST
- External cron (cron-job.org) calling `workflow_dispatch` via GH API — near-zero delay, €0
- Cloudflare Worker cron trigger — near-zero delay, €0
Also shift Dead Man's Switch to 1 hour after pipeline cron to avoid false alarms.

---

## Technical Debt

| Item | Effort | Priority |
|---|---|---|
| Groq sometimes duplicates brief content | 1h | Medium — add response post-processing |
| Static page content classified as signals | ✅ Fixed | Score-0 filter + CRITICAL FILTER in prompt |
| ~~`datetime.utcnow()` deprecation in storage module~~ | ✅ Fixed | `datetime.now(UTC)` + parameterized SQL |
| Farmland Partners URL always fails | 30min | Low — switch to SERP or remove |
| No retry on Telegram send failure | 1h | Low — add tenacity retry |
| ~~RSS module exists but unused~~ | ✅ Fixed | RSS active, 33 targets with feeds |
| `_pool` accessed directly from linker | 30min | Low — add pool property to Database |
| Integration tests don't clean up DB state | 1h | Low — add test fixtures with rollback |

---

## Metrics to Track

Once the pipeline runs for 1-2 weeks, evaluate:

| Metric | Target | How to Check |
|---|---|---|
| Signals/day | 5-15 new | `SELECT count(*) FROM signals WHERE scraped_at > NOW() - '1 day'` |
| Dedup rate | 40-70% | Check `scrape_logs.signals_deduped` |
| Score 4-5 signals/week | 3-5 | `SELECT count(*) FROM signals WHERE relevance_score >= 4 AND scraped_at > NOW() - '7 days'` |
| Brief usefulness | Founder acts on ≥1 action/week | Ask founder |
| Pipeline uptime | >95% daily runs succeed | `SELECT count(*) FILTER (WHERE status='success') * 100.0 / count(*) FROM scrape_logs` |
| API quota usage | <50% on any provider | Check provider dashboards |

---

## Decision Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-03-29 | Monitor target customers, not competitors | Founder's CSV is ICP list; sales opportunities > competitive defense |
| 2026-03-29 | No frontend for MVP | Telegram covers 100% of use case for 1-3 users |
| 2026-03-29 | No email delivery | Founder explicitly approved Telegram-only in overview |
| 2026-03-29 | Public GitHub repo | Unlimited CI minutes; code is not a competitive secret |
| 2026-03-29 | Cerebras (Qwen 3 235B) as fallback | Llama 3.3 70B removed from Cerebras; Qwen 3 is better model anyway |
| 2026-03-29 | Custom circuit breaker over pybreaker | pybreaker has broken Tornado dependency |
| 2026-03-30 | Cron 1x/day at 08:00 CET | 3x/day was overkill; saves CI minutes and API quota |
| 2026-03-30 | Brief threshold min_score=1 | Score≥3 was too restrictive; always send a brief if signals exist |
| 2026-04-06 | Multi-recipient Telegram delivery | Founder @easavin added; comma-separated TELEGRAM_CHAT_ID |
| 2026-04-06 | Event-driven signal filter (score 0) | Founder feedback: static page descriptions are noise, only classify actual events |
| 2026-04-08 | Dual intelligence (customer + competitor) | Founder provided CSV with 124 targets (EU + US); monitor both ICP and competitors |
| 2026-04-08 | Contact discovery for customers only | Serper budget savings: no LinkedIn lookups for competitors |
| 2026-04-08 | Competitor signals capped at 5 in brief | Prevent competitor noise from dominating the Battlefield Brief |
| 2026-04-08 | Deprecate greenscanalpha/ | Was design-only prototype (no code), all useful data migrated |
