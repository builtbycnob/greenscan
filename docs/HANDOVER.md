# GreenScan — Handover Document

**Project:** GreenScan — Automated Market Intelligence Pipeline
**Client:** Green Growth Innovations (Evgeny Savin, @easavin)
**Team:** Group A — Dusan, Corrado, Vittorio, Tanguy
**Date:** May 5, 2026 (initial draft April 20; refreshed for handover meeting)
**Course:** ESADE I2P, April 2026

---

## 1. What GreenScan Is

GreenScan is a fully automated market intelligence pipeline that monitors 120 target companies (67 potential customers and 53 competitors) in the EU and US agriculture sector. Every morning at 06:00 CEST, it delivers a Battlefield Brief to the founder's Telegram with two sections:

- **Opportunity Radar** — sales signals from potential customers: expansions, tech investments, leadership changes, vendor searches
- **Competitive Intelligence** — threat signals from competitors: product launches, funding rounds, market moves, key hires

The system runs entirely on free-tier services. Operating cost: **zero euros per month**.

### How It Works

The pipeline runs daily on GitHub Actions and follows 9 automated stages:

1. **SCRAPE** — Crawl4AI (web) + feedparser (RSS) scan 107 target company newsrooms
2. **DEDUP** — SHA256 content hash filters signals already seen in previous runs
3. **PRE-FILTER** — Drops content that lacks event verbs ("launches", "raises", "partners"…) or is too short — saves ~50% of LLM calls on static pages (added May 2026)
4. **CLASSIFY** — 3-tier LLM (Groq → Cerebras → Gemini) scores each signal 0-5 with category. Auto-retries on transient 5xx errors and throttles Cerebras to stay inside reduced free-tier limits.
5. **LINK** — pg_trgm fuzzy matching connects signals to known companies/contacts
6. **CONTACTS** — Serper.dev LinkedIn lookup finds decision-makers for high-value customer signals
7. **STORE** — All signals, contacts, and metadata stored in Neon Postgres
8. **BRIEF** — Gemini 2.5 Flash (or Groq fallback) generates the dual-section Battlefield Brief
9. **DELIVER** — Telegram Bot API sends brief (auto-chunked under 4096 chars) to configured recipients

### Production Metrics (as of May 5, 2026)

| Metric | Value |
|--------|-------|
| Briefs delivered | 32 (daily since April 1, 2026) |
| Database size | ~15 MB of 500 MB free tier |
| Dedup rate | ~92% (system filters previously seen content) |
| Pre-filter ratio | ~50% (only event-driven signals reach the classifier) |
| Pipeline uptime — Apr 1 to Apr 22 | ~88% (early stable phase) |
| Pipeline uptime — Apr 22 to May 4 | ~50% (LLM provider degradation period — see §4.3) |
| Pipeline uptime — post May 5 hardening | TBC (fixes shipped morning of handover, validation in progress) |

**Honest note on the recent dip:** In late April two upstream LLM providers degraded — Cerebras silently deprecated our model, and Gemini began returning frequent transient `503`s. This caused ~50% of daily runs to abort. Four resilience fixes shipped on May 5 (retry-on-5xx, signal pre-filter, switch Cerebras model, brief tightening + Telegram chunker fixes) — see §4.3 for the full list. Post-fix uptime will only be visible after a few days of runs.

---

## 2. Accesses

### 2.1 GitHub Repository

- **URL:** https://github.com/builtbycnob/greenscan
- **Visibility:** Public (unlimited CI minutes)
- **Access:** Evgeny has been added as collaborator with write access

The repository contains all source code, configuration, documentation, and CI/CD workflows. No external dependencies beyond the API keys listed below.

### 2.2 API Keys and Secrets

All API keys are configured as GitHub Actions Secrets (Settings → Secrets and variables → Actions). They are also stored in the local `.env` file (not committed to git).

| Service | Secret Name | Where to Manage | Free Tier Limits | Model in use |
|---------|-------------|-----------------|------------------|--------------|
| Groq (primary LLM) | `GROQ_API_KEY` | console.groq.com | 1,000 requests/day, 100K tokens/day, 12K tokens/min | `llama-3.3-70b-versatile` |
| Cerebras (fallback LLM) | `CEREBRAS_API_KEY` | inference.cerebras.ai | Nominal 14,400 RPD / 1M TPD; reduced RPM on "high demand" models — we throttle to ≤10 RPM | `gpt-oss-120b` |
| Gemini (briefs + 3rd tier) | `GEMINI_API_KEY` | aistudio.google.com | 250 requests/day | `gemini-2.5-flash` (brief), `gemini-2.5-flash-lite` (classify) |
| Neon Postgres | `NEON_DATABASE_URL` | console.neon.tech | 0.5 GB storage, 100 compute-hours/month | Postgres 17 (us-east-1) |
| Telegram Bot | `TELEGRAM_BOT_TOKEN` | @BotFather on Telegram | Unlimited | — |
| Telegram Recipients | `TELEGRAM_CHAT_ID` | Comma-separated chat IDs | — | — |
| Serper.dev (contacts) | `SERPER_API_KEY` | serper.dev | 2,500 lifetime credits | — |

**Action required for handover:** Transfer ownership of the following accounts to Evgeny or create new keys under his accounts:
1. **Groq** — Create account at console.groq.com, generate API key, replace in GitHub Secrets
2. **Cerebras** — Create account at inference.cerebras.ai, same process
3. **Gemini** — Create at aistudio.google.com with a Google account
4. **Neon** — Transfer project ownership or create new project and run migration
5. **Serper** — Create account at serper.dev (2,500 free credits on signup)
6. **Telegram Bot** — Already owned by Evgeny (no transfer needed)

### 2.3 Neon Database

- **Project:** GreenScan on Neon free tier
- **Region:** AWS us-east-1
- **Connection:** Pooled via PgBouncer (connection string in `NEON_DATABASE_URL`)
- **Schema:** 6 tables — `targets`, `companies`, `contacts`, `signals`, `briefs`, `scrape_logs`
- **Migration file:** `pipeline/storage/migrations/001_initial.sql`

To recreate the database on a new Neon account:
```bash
# 1. Create a new Neon project at console.neon.tech
# 2. Copy the pooled connection string
# 3. Run the migration:
psql "YOUR_NEW_CONNECTION_STRING" < pipeline/storage/migrations/001_initial.sql
# 4. Update NEON_DATABASE_URL in .env and GitHub Secrets
```

### 2.4 GitHub Actions

Four automated workflows:

| Workflow | Schedule | Purpose |
|----------|----------|---------|
| `daily_pipeline.yml` | 04:00 UTC daily | Runs the full pipeline, delivers brief |
| `dead_mans_switch.yml` | 05:00 UTC daily | Alerts on Telegram if pipeline didn't run or no brief |
| `test.yml` | On every push | Lints code + runs 37 unit tests |
| `keepalive.yml` | 1st of each month | Pushes timestamp to prevent GitHub from disabling crons |

All secrets are already configured in the repository.

---

## 3. Step-by-Step Instructions

### 3.1 Daily Use (No Technical Knowledge Required)

**You don't need to do anything.** The pipeline runs automatically every morning. The Battlefield Brief arrives in your Telegram by ~06:30 CEST.

If you don't receive a brief by 07:00 CEST:
1. Check Telegram — the dead man's switch should have sent an alert
2. If no alert either, go to GitHub → Actions tab → check if workflows are running
3. If workflows are disabled, push any commit to reactivate them

### 3.2 Adding a New Target Company

1. Edit `targets.yaml` and add an entry:
```yaml
- name: "New Company Name"
  type: customer          # or competitor
  region:
    - EU                  # or US, or both
  industry: direct_farm_operator
  priority: HIGH          # or MEDIUM, LOW
  monitoring: direct_scrape
  website: https://www.newcompany.com
  contact_lookup: true    # false for competitors
  scrape_urls:
    - https://www.newcompany.com/news
    - https://www.newcompany.com/newsroom
  rss_feeds: []
  serp_queries: []
  decision_maker_titles:
    - CEO
    - VP Sales
  crop_focus: Wheat, Corn
  why_icp: "Short explanation of why this company matters"
  hq: Country or City
```

2. Commit and push:
```bash
git add targets.yaml
git commit -m "feat: add New Company to targets"
git push
```

3. The pipeline will pick it up on the next daily run automatically.

### 3.3 Removing a Target Company

Delete the entry from `targets.yaml`, commit, and push. Historical signals for that company remain in the database.

### 3.4 Changing Telegram Recipients

1. Get the chat ID of the new recipient:
   - Have them message the Telegram bot
   - Check `https://api.telegram.org/bot<TOKEN>/getUpdates` for their chat ID
2. Update `TELEGRAM_CHAT_ID` in GitHub Secrets (Settings → Secrets → Actions)
   - Multiple recipients: comma-separated, e.g., `128370791,281584044`

### 3.5 Running the Pipeline Manually

```bash
# From GitHub (recommended)
# Go to Actions → Daily Pipeline → Run workflow

# From command line (requires local setup)
uv run python -m pipeline daily

# Demo mode (3 targets, stdout, no DB)
uv run python -m pipeline demo
```

### 3.6 Modifying the Brief Format

Edit `pipeline/brief/generator.py`. The `BRIEF_SYSTEM_PROMPT` (line 14) controls the structure and tone. Changes take effect on the next pipeline run.

### 3.7 Rotating API Keys

1. Generate new key on the provider's dashboard
2. Update in GitHub → Settings → Secrets → Actions
3. Update local `.env` file
4. Test: `uv run python -m pipeline demo`

Full rotation guide: see `RUNBOOK.md` in the repository.

### 3.8 Local Development Setup

```bash
# Clone the repository
git clone https://github.com/builtbycnob/greenscan.git
cd greenscan

# Install dependencies (requires Python 3.12+ and uv)
uv sync

# Copy and fill environment variables
cp .env.example .env
# Edit .env with your API keys

# Run tests
uv run python -m pytest -x

# Run demo pipeline
uv run python -m pipeline demo
```

---

## 4. What to Expect (Service Levels)

| Item | Expectation |
|------|-------------|
| **Brief delivery** | Every morning between ~06:30 and ~07:30 CEST (cron at 04:00 UTC, run takes 6-9 min). Arrives via Telegram. |
| **Signal volume** | 30-60 new signals stored per day; ~10-15 above brief threshold (customer ≥3, competitor ≥4). The brief itself caps at 15 signals max. |
| **If no brief arrives** | The dead man's switch alerts you on Telegram by ~07:00 CEST. If no alert either, check GitHub Actions. |
| **Contact discovery** | 5-15 LinkedIn contacts per brief for high-scoring customer signals (score ≥3). |
| **Dedup behavior** | 92%+ of scraped content is filtered as already-seen. This is normal — it means the system is working. |
| **Maintenance required** | None for daily operation. Rotate API keys if a provider changes their policy; switch Cerebras model if it gets deprecated again. |

---

## 5. Cost-Benefit Analysis

### What GreenScan replaces

| Alternative | Cost | Limitation |
|-------------|------|-----------|
| Manual newsroom scanning | ~1.5h/day of founder time | Not scalable past 10 companies; misses signals outside work hours |
| Google Alerts | Free | No classification, no scoring, no contacts, high noise, no brief |
| Crayon / Klue | €20,000-30,000/year | Enterprise-grade; overkill for a pre-seed startup with 1-3 users |
| Part-time research assistant | ~€300/month | Manual, inconsistent, limited coverage |

### What GreenScan costs

**€0/month.** All services run on free tiers with no credit card required. The only finite resource is Serper.dev (2,500 lifetime credits for LinkedIn lookups), which lasts ~4 months at current usage.

### Estimated value

- **Time saved:** ~1.5 hours/day of manual scanning across 120 companies
- **Speed advantage:** Signals detected within hours of publication, not days or weeks
- **Coverage:** 107 actively monitored newsrooms — impossible to match manually
- **Contact discovery:** 184 LinkedIn decision-makers identified automatically

---

## 6. Top Discoveries (Proof of Value)

These are real signals detected by GreenScan in production — not test data.

### Competitive Threats

| Date | Company | Signal | Why It Matters |
|------|---------|--------|---------------|
| Apr 9 | **FarmTRX** | Universal retrofit yield monitor with John Deere Operations Center API integration | **Direct competitor to Green Growth's core product.** Same value proposition (retrofit, any combine), now integrated with the largest equipment ecosystem. |
| Apr 13 | **FarmTRX** | Delivering yield data to Kernel's 1.2M acre mega-farm | FarmTRX scaling to enterprise agricultural operations — validates the market but increases competitive pressure. |
| Apr 10 | **CLAAS** | Launched JAGUAR 1000 and XERION 12 Series | Major OEM expanding precision ag hardware lineup. |

### Sales Opportunities

| Date | Company | Signal | Why It Matters |
|------|---------|--------|---------------|
| Apr 9 | **BASF (xarvio)** | Launched xarvio FIELD MANAGER for Grapes + rice yield guarantee | BASF investing heavily in digital farming — potential partner or customer for yield data integration. |
| Apr 9 | **Climate FieldView (Bayer)** | Integration with Rantizo's AcreConnect for drone application maps | FieldView expanding ecosystem; Green Growth's yield data could complement this platform. |
| Apr 16 | **CropX** | Launched Apex sensor + AI-Powered CropX Vision | CropX building a soil-to-canopy data platform; yield monitoring is a natural complement. |
| Apr 9 | **Sentera** | SMARTSCRIPT Weeds early access fully enrolled | Strong market demand for precision ag analytics; signals a receptive buyer environment. |

### Most Active Companies (by signal volume)

Taranis (24 signals), Ceres Partners (16), Agrivi (15), FarmTRX (11), FBN (11) — these companies are producing the most market-moving news in the precision ag space.

---

## 7. Insights Discovered

### 7.1 Signal Quality

- **~50% of pre-filter input is static page content** — corporate boilerplate, navigation pages, "about us" copy. The new pre-filter (May 2026) drops these *before* the LLM sees them, halving classifier API spend.
- **~59% of remaining classified signals fall into "other"** — corporate news without precision-ag relevance (sponsorships, generic PR). Scored 0 by the classifier and ignored.
- **Score threshold history:** Started at customer ≥3 (too strict, empty briefs), dropped to ≥1 (noise), settled on ≥2 in mid-April, then back up to **≥3 customer / ≥4 competitor on May 5** (Gemini was generating ~20K-char briefs with the looser thresholds — last Telegram chunks were dropped). The brief now also caps at 15 total signals.
- **FarmTRX is a direct competitor** — discovered via the pipeline. They offer a universal retrofit yield monitor with John Deere Operations Center API integration. This is the closest competitor to Green Growth's core product we found.

### 7.2 Dedup Rate Growth

The dedup rate is ~92% and rising. Most company newsrooms update weekly, not daily. After 2-3 months, nearly all daily signals will be duplicates of previously seen content. **Mitigation:** Add SERP monitoring (Google News queries) for fresher signals from third-party sources.

### 7.3 LLM Provider Reliability — and the May 2026 hardening

What we observed across April:
- **Groq** (`llama-3.3-70b-versatile`) is fast but hits its 12K **tokens-per-minute** cap after only 2-3 batches — drains in seconds, not in calls. Drain-and-switch handles this correctly, so Groq simply does the first 2-3 batches and hands off.
- **Cerebras** silently deprecated `qwen-3-235b-a22b-instruct-2507` and then `llama-3.3-70b` (Feb 16, 2026). After the deprecation our calls were returning `404 Not Found`. Their recommended replacement is `gpt-oss-120b`, but it carries a "temporarily reduced" free-tier RPM. We mitigated by switching to `gpt-oss-120b` and adding a 6-second inter-call delay (≤10 RPM).
- **Gemini 2.5 Flash** occasionally returns `503 Service Unavailable` on transient Google-side load. Without retry, a single transient error aborted the whole pipeline. We now retry up to 3 times with exponential backoff (1s/2s/4s).

Four resilience fixes shipped May 5, 2026 — these are the changes the founder's first stable runs will benefit from:

| # | What | Where it lives |
|---|---|---|
| 1 | Retry-on-5xx with exponential backoff (3 attempts) on Cerebras + Gemini classify calls and Gemini brief call | `pipeline/classifier/llm.py:_retry_on_5xx`, `pipeline/brief/generator.py:_generate_with_gemini` |
| 2 | Pre-filter signals before LLM classification — drop short/static/no-event-verb content | `pipeline/classifier/prefilter.py` |
| 3 | Switch Cerebras model to `gpt-oss-120b` + throttle ≤10 RPM | `pipeline/config.py:cerebras_model`, `cerebras_inter_call_delay` |
| 4 | Brief tightening: hard 400-word cap, score floors raised (customer 2→3, competitor 3→4), max-15 total signals; Telegram chunk size 4000→3500 to leave slack for markdown escapes; fixed `parse_mode=None` plaintext-fallback bug | `pipeline/brief/generator.py`, `pipeline/config.py`, `pipeline/delivery/telegram.py` |

Together these fixes target the two failure modes seen in late April: pipeline aborts (now retried) and brief truncation in Telegram (now sized to fit).

### 7.4 Budget Sustainability

| Resource | Limit | Current Usage | Runway |
|----------|-------|---------------|--------|
| Groq | 1,000 RPD / 100K TPD / 12K TPM | 2-3 calls/run (TPM-bound) | Indefinite (resets daily) |
| Cerebras | 14,400 RPD / 1M TPD nominal — reduced RPM on `gpt-oss-120b` | We throttle to ≤10 RPM, ~10 calls/run | Indefinite (rate-bound, not quota-bound) |
| Gemini | 250 RPD | 5-15 classify calls/run + 1 brief call | Indefinite |
| Neon | 0.5 GB | ~15 MB | ~3-4 years at current rate |
| Serper | 2,500 lifetime | ~20/day when contacts found | ~4 months at max usage |
| GH Actions | Unlimited (public repo) | ~6-9 min/run | Indefinite |

**Serper is the only resource that depletes.** At maximum usage (20 lookups/day), the 2,500 lifetime credits last ~4 months. Options when exhausted:
- Create a new Serper account (2,500 more free credits)
- Switch to Hunter.io (50 free lookups/month) or Apollo.io (free tier)
- Disable contact discovery (pipeline continues without it)

---

## 8. Known Limitations

| Limitation | Impact | Workaround |
|------------|--------|------------|
| 13 targets are serp-only | Zero signals for these companies | Build SERP monitoring module (top of backlog) |
| LLM provider deprecations are silent | Cerebras can change/retire models without warning — pipeline gets `404`s | Subscribe to `inference-docs.cerebras.ai/support/deprecation` updates; the 3-tier fallback means at worst the pipeline becomes Gemini-only |
| Free-tier RPM caps on "high demand" models | Cerebras throttle is conservative (≤10 RPM) which adds ~1 min to pipeline runtime | Acceptable trade-off — runtime is not user-facing |
| No real-time alerts | Score-5 signals wait until next morning | Add webhook-triggered alerts for critical signals (in backlog) |
| Contact lookup limited to 20/day | Some briefs miss decision-makers | Increase when budget allows |
| No web dashboard | Data only accessible via DB queries or Telegram | Build Streamlit dashboard (in backlog) |

---

## 9. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **LLM provider deprecates the model we're using** | High (already happened twice with Cerebras in Feb 2026) | High — calls return `404`, pipeline classifies on Gemini only | Update `cerebras_model` in `pipeline/config.py` to the new official name (see `inference-docs.cerebras.ai/models/overview`); commit + push |
| **LLM provider changes free tier limits** | Medium | High — pipeline stops classifying | 3-tier fallback already in place. If all three change: Hugging Face Inference API (free) or local models via Ollama. |
| **Target company changes website** | High (expected) | Low — one company loses coverage | Scrape failures are logged. RUNBOOK has troubleshooting steps. Update URL in `targets.yaml`. |
| **Dedup rate reaches 99%** | High (2-3 months) | Medium — briefs become empty | Add SERP monitoring for third-party news sources. Top item on backlog. |
| **Serper credits exhausted** | Medium (4 months) | Low — contacts stop, pipeline continues | Create new account, switch to Hunter.io, or disable contact discovery. |
| **GitHub disables cron** | Low (keep-alive prevents this) | Critical — pipeline silently dies | Keep-alive workflow pushes monthly commit. If it fails, any manual push reactivates. |
| **Neon DB reaches 0.5 GB** | Very low (4+ years) | Medium — inserts fail | Archive old signals (>6 months) or upgrade to Pro ($19/month). |
| **Telegram bot token revoked** | Very low | High — no delivery | Re-create via @BotFather, update `TELEGRAM_BOT_TOKEN` in GitHub Secrets. |

---

## 10. Repository Structure

```
greenscan/
├── pipeline/                      # Core application
│   ├── scraper/                   # Web + RSS + SERP scrapers
│   ├── classifier/                # 3-tier LLM classification
│   │   ├── llm.py                 # Provider fallback + retry-on-5xx + Cerebras throttle
│   │   ├── prefilter.py           # Event-verb pre-filter (added May 2026)
│   │   ├── categorizer.py         # Batch classification + parsing
│   │   └── prompts.py             # Classifier system prompt + rubrics
│   ├── enrichment/                # Dedup, contacts, entity linking
│   ├── storage/                   # Database operations + migrations
│   ├── brief/                     # Brief generator (with retry)
│   ├── delivery/                  # Telegram delivery
│   ├── config.py                  # All configuration (env-based)
│   └── main.py                    # Pipeline orchestrator
├── tests/                         # 62 tests (51 unit + 11 integration)
├── targets.yaml                   # 120 monitored targets (67 customers + 53 competitors)
├── .github/workflows/             # 4 automated workflows
├── docs/                          # Research, changelog, overview, this handover
├── CLAUDE.md                      # AI-assistant project context
├── BACKLOG.md                     # Prioritized product backlog
└── RUNBOOK.md                     # Operator handbook
```

---

## 11. Prioritized Backlog (What to Build Next)

### Priority 1 — High Impact, Low Effort

1. **SERP Monitoring** — Add Google News queries for the 13 serp-only targets. `serp.py` already handles Serper API calls; extend it for news signal collection. (~3h)
2. **SEC/IR Filings** — Monitor public company earnings (Farmland Partners, Lamb Weston, Bayer) via SEC EDGAR RSS feeds. (~2h)
3. **Contact Enrichment Scaling** — When Serper credits run out, integrate Hunter.io (50 free/month) or Apollo.io for email discovery. (~2h)

### Priority 2 — Medium Impact

4. **Telegram Bot Commands** — `/latest`, `/competitor Bayer`, `/brief`, `/stats` — upgrade from send-only to interactive. (~3h)
5. **Brief Personalization** — Weekly summary on Monday, daily incremental on other days. (~2h)
6. **Industry News Sources** — AgFunderNews, PotatoPro, Future Farming — catch third-party mentions of target companies. (~2h)

### Priority 3 — Future Vision

7. **NL-to-SQL** — Let the founder query the database in natural language via Telegram. Read-only Postgres role already created. (~4h)
8. **Web Dashboard** — Streamlit on Community Cloud (free). Signal feed, brief archive, pipeline health. (~4h)
9. **CRM Integration** — Push qualified leads and contacts directly to a CRM system. (Effort TBD)

Full backlog with effort estimates: see `BACKLOG.md` in the repository.

---

## 12. Key Files Reference

| File | Purpose | When to Edit |
|------|---------|-------------|
| `targets.yaml` | List of monitored companies | Adding/removing targets |
| `pipeline/config.py` | All thresholds and settings | Tuning score thresholds, batch sizes, Cerebras throttle, brief score floors, brief total cap |
| `pipeline/brief/generator.py` | Brief format and prompt (`BRIEF_SYSTEM_PROMPT`) | Changing brief structure, tone, or word cap |
| `pipeline/classifier/prefilter.py` | Event-verb dictionary + min length | Tightening or loosening pre-filter (e.g. add new verbs) |
| `pipeline/classifier/prompts.py` | Classification rubrics | Tuning what counts as relevant |
| `pipeline/delivery/telegram.py` | Chunker + parse mode | Tuning `MAX_MESSAGE_LENGTH` if delivery still truncates |
| `.env` | Local API keys | Rotating credentials locally |
| `.github/workflows/daily_pipeline.yml` | Cron schedule | Changing pipeline run time |
| `RUNBOOK.md` | Operator handbook | Reference for troubleshooting |
| `BACKLOG.md` | Product roadmap | Planning next features |

---

## 13. Handover Checklist

- [ ] Transfer GitHub repository ownership (or confirm collaborator access)
- [ ] Transfer or recreate Groq API key under client's account
- [ ] Transfer or recreate Cerebras API key under client's account
- [ ] Transfer or recreate Gemini API key under client's account
- [ ] Transfer or recreate Neon database (or transfer project ownership)
- [ ] Transfer or recreate Serper.dev account
- [ ] Confirm Telegram bot is owned by client
- [ ] Confirm all GitHub Actions secrets are set
- [ ] Verify pipeline runs successfully after transfer
- [ ] Walk through RUNBOOK.md with client
- [ ] Walk through BACKLOG.md priorities with client
- [ ] Confirm client can add/remove targets independently

---

*GreenScan — ESADE I2P, Group A, April 2026*
*Repository: github.com/builtbycnob/greenscan*
