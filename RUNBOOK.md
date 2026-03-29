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
| "All providers exhausted" | All 3 LLM APIs are down or rate-limited. Wait and retry. |
| Groq 429 errors | Normal — Cerebras handles overflow automatically. |
| Telegram not delivered | Check bot token hasn't expired. Re-create with @BotFather if needed. |
| Brief not generated | No signals scored >= 3. This is normal if no relevant news today. |
| Pipeline runs but no new signals | Dedup working correctly. Content hasn't changed since last run. |
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
GitHub Actions (06:17, 12:17, 18:17 UTC)
  → pipeline/main.py run_daily()
    → scraper/web.py (Crawl4AI, 7 URLs)
    → enrichment/dedup.py (SHA256 vs DB)
    → classifier/llm.py (Groq → Cerebras → Gemini)
    → classifier/categorizer.py (9 categories)
    → enrichment/linker.py (pg_trgm fuzzy match)
    → storage/db.py (Neon Postgres)
    → brief/generator.py (Groq or Gemini)
    → delivery/telegram.py (httpx)
```

## LLM Provider Limits

| Provider | Model | Daily Limit | Tokens/Min |
|---|---|---|---|
| Groq (primary) | Llama 3.3 70B | 1,000 RPD | 12,000 |
| Cerebras (fallback) | Qwen 3 235B | 14,400 RPD | 30,000 |
| Gemini (brief gen) | 2.5 Flash | 250 RPD | 250,000 |

Fallback is automatic. No manual intervention needed.
