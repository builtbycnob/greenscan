# GreenScan — Recommended Stack (Cheat Sheet)

> One-page reference. Total monthly cost: **€0**.

---

## Stack

| Componente | Tecnologia | Free Tier | Note |
|---|---|---|---|
| **Web Scraping** | Crawl4AI 0.8.x | Illimitato | Stealth, JS rendering, markdown output |
| **RSS** | newspaper4k + feedparser | Illimitato | Full article extraction |
| **SERP** | Serper.dev | 2,500 query/mese | Weekly deep scan (~130 query/mese) |
| **LLM primario** | Groq (Llama 3.3 70B) | **1,000 req/giorno**, 30 RPM, 6K TPM | ~200 req/giorno usati, margine stretto |
| **LLM fallback** | Gemini 2.5 Flash | 250 RPD | Auto-switch dopo 3 errori Groq |
| **Database** | Neon Postgres | 0.5 GB, 100 CU-hrs (raddoppiati ott 2025) | pg_trgm, JSONB, scale-to-zero |
| **Scheduling** | GitHub Actions cron | 2,000 min/mese | ~300-900 min/mese usati |
| **Notifiche** | Telegram Bot API | Illimitato | Brief + alert score 5 |
| **Email backup** | Resend | 3,000 email/mese | Fallback se Telegram down |
| **Frontend** | Next.js 14 + Vercel | 100 GB bandwidth | App Router, API routes |
| **NL-to-SQL** | Prompt engineering + Groq | (incluso in LLM) | Schema injection + few-shot |
| **Dedup** | SHA256 in Postgres | — | UNIQUE index, zero overhead |
| **Fuzzy search** | pg_trgm (Postgres) | — | Built-in Neon |

---

## Architettura

```
GitHub Actions (3x/giorno)
  │
  ▼
Pipeline Python ──► Crawl4AI + RSS + SERP
  │                       │
  │              SHA256 dedup (40-60% drop)
  │                       │
  │              Groq LLM: classify + score + entities
  │                       │
  │                       ▼
  │              Neon Postgres (6 tabelle)
  │                       │
  │              Groq LLM: genera brief
  │                       │
  ▼                       ▼
Telegram + Email    Next.js/Vercel (CRM)
                          │
                    NL-to-SQL (Groq)
```

---

## Database (6 tabelle)

| Tabella | Scopo | Righe stimate (anno 1) |
|---------|-------|------------------------|
| `competitors` | 30 competitor tracciati | 30 |
| `companies` | Superset aziende menzionate | ~500 |
| `contacts` | Persone con ruolo/azienda | ~1,000 |
| `signals` | Segnali classificati | ~10,000 |
| `briefs` | Brief giornalieri markdown | ~365 |
| `scrape_logs` | Health monitoring | ~1,100 |

---

## Comandi Essenziali

### Pipeline

```bash
# Run manuale
python -m pipeline.main daily      # Pipeline giornaliero
python -m pipeline.main weekly     # Deep scan SERP
python -m pipeline.main demo       # Day 1 demo (3 competitor, stdout)

# GitHub Actions trigger manuale
gh workflow run daily_pipeline.yml
gh workflow run weekly_deep_scan.yml
```

### Database

```bash
# Connessione
psql $NEON_DATABASE_URL

# Query utili
SELECT count(*) FROM signals WHERE scraped_at > NOW() - INTERVAL '1 day';
SELECT category, count(*) FROM signals GROUP BY category;
SELECT * FROM scrape_logs ORDER BY started_at DESC LIMIT 5;
```

### Competitor Management

```yaml
# competitors.yaml — aggiungere un competitor:
- name: "NuovoCompetitor"
  tier: 2
  sector: "precision_ag"
  scrape_urls:
    - "https://nuovocompetitor.com/blog"
    - "https://nuovocompetitor.com/news"
  rss_feeds:
    - "https://nuovocompetitor.com/feed"
  serp_queries:
    - "NuovoCompetitor AgTech news"
```

### Frontend (Next.js)

```bash
cd frontend
npm run dev          # Dev locale (http://localhost:3000)
npx vercel           # Deploy manuale
npx vercel --prod    # Deploy produzione
```

---

## Secrets (GitHub)

| Secret | Dove trovarlo |
|--------|---------------|
| `NEON_DATABASE_URL` | Neon dashboard → Connection Details |
| `GROQ_API_KEY` | console.groq.com → API Keys |
| `GEMINI_API_KEY` | aistudio.google.com → Get API Key |
| `SERPER_API_KEY` | serper.dev → Dashboard |
| `TELEGRAM_BOT_TOKEN` | @BotFather su Telegram |
| `TELEGRAM_CHAT_ID` | Invia messaggio al bot, usa getUpdates API |
| `RESEND_API_KEY` | resend.com → API Keys |

---

## Milestones

| Quando | Cosa | Verifica |
|--------|------|----------|
| **Day 1** | Scrape 3 competitor + classifica → stdout | `python -m pipeline.main demo` |
| **Week 1** | Pipeline completo + brief su Telegram | Brief arriva ogni giorno |
| **Week 2** | CRM frontend su Vercel | Dashboard accessibile |
| **Week 3** | 30 competitor + NL query + SERP | Sistema completo |

---

## Rischi Critici

| Rischio | Mitigazione |
|---------|-------------|
| **GH Actions minuti** (~750-1,040/mese su 2,000) | Cache Playwright con `actions/cache`, monitorare da settimana 1, fallback: repo pubblico |
| **Groq free tier ridotto** — ora 1,000 RPD (era 14,400), 6K TPM | Batch piccoli (3-5 segnali), Gemini fallback essenziale, verificare su console.groq.com |
| **Neon 0.5GB** (~80-200MB anno 1 con indici GIN) | Usare `jsonb_path_ops`, monitorare in `/api/health`, archiviare segnali vecchi score <= 2 |
| **Pipeline failure silenziosa** | Alert Telegram su failure (US-02.8, XS effort) |
| **Competitor data entry** (1-2 giorni lavoro manuale) | Story dedicata US-02.7, inizia Sprint 1 |

## Troubleshooting

| Problema | Soluzione |
|----------|----------|
| Groq rate limit (429) | Attendi 60s, o switch a Gemini fallback (automatico) |
| Neon cold start lento | Prima query dopo inattività ~1-2s, normale |
| Crawl4AI 403/blocked | Verifica stealth mode, aggiungi delay tra request |
| Telegram messaggio troncato | Brief > 4096 char viene splittato automaticamente |
| GH Actions cron in ritardo | Normale (±5-15 min), non è un problema |
| "No module named pipeline" | Assicurati di aver fatto `pip install -e .` |
| Neon CU-hours esaurite | Scale-to-zero dovrebbe bastare, altrimenti ottimizza query |
| Pipeline fallita, nessun alert | Verificare che US-02.8 sia implementata, controllare scrape_logs |
