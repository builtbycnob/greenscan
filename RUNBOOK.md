# GreenScan — Operator Runbook

## Quick Reference

```bash
# Run pipeline manually (demo: 3 targets, stdout)
uv run python -m pipeline demo

# Run full pipeline (all targets, DB, Telegram)
uv run python -m pipeline daily

# Trigger from GitHub Actions
gh workflow run daily_pipeline.yml
```

## Adding a New Target Company

1. Edit `targets.yaml` and add an entry:
```yaml
- name: "New Company"
  industry: direct_farm_operator  # or food_processor, farmland_investor, etc.
  priority: HIGH  # or MEDIUM
  monitoring: direct_scrape  # or serp_only, sec_ir
  website: "https://www.newcompany.com"
  scrape_urls:
    - "https://www.newcompany.com/news"
  rss_feeds: []
  serp_queries:
    - "New Company precision agriculture"
```

2. Test locally: `uv run python -m pipeline demo`
3. Commit and push — the cron will pick it up automatically.

## Debugging Pipeline Failures

### Check Recent Runs
```sql
SELECT run_id, status, signals_new, signals_deduped, duration_ms, error_message
FROM scrape_logs ORDER BY started_at DESC LIMIT 10;
```

### Check Signal Counts
```sql
SELECT date(scraped_at), count(*) FROM signals
GROUP BY date(scraped_at) ORDER BY 1 DESC LIMIT 7;
```

### Common Issues

| Problem | Solution |
|---|---|
| "No signals scraped" | Target URLs may have changed. Check manually. |
| "All providers exhausted" | All 3 LLM APIs are down or rate-limited. Retry-on-5xx (3 attempts) is automatic; if it still fails, all three providers had simultaneous transient errors. Wait and retry. |
| Cerebras `404 Not Found` | Cerebras deprecated the model. Check `inference-docs.cerebras.ai/models/overview`, update `cerebras_model` in `pipeline/config.py`, commit + push. |
| Cerebras `429 Too Many Requests` after 1-2 calls | Free-tier RPM cap on a "high demand" model is lower than 10. Increase `cerebras_inter_call_delay` in `pipeline/config.py` (e.g., 6.0 → 10.0). |
| Groq 429 errors | Normal — Cerebras / Gemini handle overflow automatically. |
| Telegram `message is too long` | Brief is too verbose for the chunker. Either lower `MAX_MESSAGE_LENGTH` further in `pipeline/delivery/telegram.py`, or tighten brief score floors / total cap in `pipeline/config.py`. |
| Telegram `unsupported parse_mode` | The plaintext fallback should now work; if it doesn't, ensure `payload.pop("parse_mode", None)` is in `_send_message` (May 2026 fix). |
| Telegram not delivered | Check bot token hasn't expired. Re-create with @BotFather if needed. |
| Telegram sent to wrong people | Check TELEGRAM_CHAT_ID in .env / GitHub Secret — comma-separated list. |
| Brief not generated | No signals scored >= customer 3 / competitor 4 (May 2026 thresholds). Static pages get score 0 and are filtered before reaching the classifier (pre-filter). |
| Pipeline runs but no new signals | Dedup working correctly. Content hasn't changed since last run. |
| Pre-filter dropping too many signals | Edit `pipeline/classifier/prefilter.py` — add verbs to `EVENT_VERB_TOKENS` or lower `MIN_CONTENT_CHARS`. |
| GitHub Actions cron stopped | Repo inactive >60 days. Push any commit to reactivate. |

### Re-run a Failed Pipeline
```bash
# From GitHub
gh workflow run daily_pipeline.yml

# Locally
uv run python -m pipeline daily
```

## Rotating Secrets

### API Keys
1. Generate new key on provider dashboard
2. Update in GitHub Settings → Secrets → Actions
3. Update local `.env` file
4. Test: `uv run python -m pipeline demo`

| Secret | Where to rotate |
|---|---|
| `GROQ_API_KEY` | console.groq.com → API Keys |
| `CEREBRAS_API_KEY` | inference.cerebras.ai → API Keys |
| `GEMINI_API_KEY` | aistudio.google.com → Get API Key |
| `NEON_DATABASE_URL` | Neon dashboard → Connection Details |
| `TELEGRAM_BOT_TOKEN` | @BotFather → /revoke then /newbot |
| `TELEGRAM_CHAT_ID` | Comma-separated IDs (e.g., `128370791,281584044`) |
| `SERPER_API_KEY` | serper.dev → Dashboard |

### Neon Database Password
1. Go to Neon dashboard → Connection Details → Reset password
2. Copy new pooled connection string
3. Update `NEON_DATABASE_URL` in GitHub Secrets AND local `.env`

## Monitoring

### Daily Checks (automated)
- Dead man's switch runs at 07:00 UTC — alerts if no brief was generated
- Pipeline failure alerts go to Telegram immediately

### Weekly Checks (manual, 5 min)
```sql
-- Signal volume trend
SELECT date(scraped_at), count(*), avg(relevance_score)::numeric(3,1)
FROM signals GROUP BY 1 ORDER BY 1 DESC LIMIT 7;

-- Dedup rate
SELECT run_id, signals_new, signals_deduped,
  round(signals_deduped::numeric / nullif(signals_new + signals_deduped, 0) * 100) as dedup_pct
FROM scrape_logs WHERE status = 'success'
ORDER BY started_at DESC LIMIT 7;

-- DB storage used
SELECT pg_size_pretty(pg_database_size(current_database()));
```

### Monthly Checks
- Review Groq/Cerebras usage on their dashboards
- Check Neon CU-hours usage (dashboard → Usage)
- Check GitHub Actions minutes (Settings → Billing)

## Architecture Overview

```
GitHub Actions (04:00 UTC daily — 06:00 CEST)
  → pipeline/main.py run_daily()
    → scraper/web.py (Crawl4AI) + scraper/rss.py (feedparser)
    → enrichment/dedup.py (SHA256 vs DB)
    → classifier/prefilter.py (event-verb filter, May 2026)
    → classifier/llm.py (Groq → Cerebras → Gemini, with retry-on-5xx)
    → classifier/categorizer.py (11 categories)
    → enrichment/linker.py (pg_trgm fuzzy match)
    → enrichment/contacts.py (Serper LinkedIn lookup)
    → storage/db.py (Neon Postgres)
    → brief/generator.py (Gemini 2.5 Flash, Groq fallback, retry-on-5xx)
    → delivery/telegram.py (httpx, multi-recipient, chunked ≤3500 char)
```

## LLM Provider Limits (current as of May 2026)

| Provider | Model | Daily Limit | Tokens/Min | Notes |
|---|---|---|---|---|
| Groq (primary) | `llama-3.3-70b-versatile` | 1,000 RPD / 100K TPD | 12K TPM | Drains in 2-3 batches |
| Cerebras (fallback 1) | `gpt-oss-120b` | Nominal 14,400 RPD / 1M TPD | reduced — we throttle to ≤10 RPM | "High demand" model with hidden RPM cap; 6s inter-call delay |
| Gemini (classify fallback + brief) | `gemini-2.5-flash-lite` (classify), `gemini-2.5-flash` (brief) | 250 RPD | n/a | Carries most classify load |

Fallback is automatic. Retry-on-5xx (3 attempts, exp backoff) covers transient Gemini/Cerebras errors. No manual intervention needed for normal operation.

### When Cerebras starts returning 404
Cerebras deprecates models periodically (last events: Feb 16, 2026). To switch:
1. Check the current free-tier model list at `inference-docs.cerebras.ai/models/overview`
2. Update `cerebras_model` in `pipeline/config.py`
3. Commit and push — pipeline picks it up on next run
