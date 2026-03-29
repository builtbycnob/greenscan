# GreenScan — Tech Stack Evaluation

> Valutazione comparativa di ogni componente dello stack. Ogni categoria presenta 3-5 opzioni con analisi free tier, pro/contro, e raccomandazione finale.
> Budget target: **€0/mese** (solo free tier).

---

## 1. Web Scraping

| Opzione | Free Tier | Pro | Contro | Costo Mensile | Raccomandazione |
|---------|-----------|-----|--------|---------------|-----------------|
| **Crawl4AI 0.8.x** | Illimitato (open source) | Stealth mode anti-bot, JS rendering (Playwright), output Markdown LLM-ready, async nativo, structured extraction | Progetto giovane, docs in evoluzione, richiede Playwright su CI | €0 | **RACCOMANDATO** |
| Scrapy | Illimitato (open source) | Maturo, enorme ecosistema, middleware pipeline | No JS rendering nativo (serve Splash/Playwright), output non LLM-ready, curva di apprendimento ripida | €0 | Alternativa solida ma over-engineered per MVP |
| Beautiful Soup + requests | Illimitato (open source) | Semplicissimo, ubiquo, ottima documentazione | Solo HTML statico, no JS rendering, no stealth, scraping manuale | €0 | Troppo basico per siti moderni |
| Apify | 5$ crediti gratuiti | Managed, anti-bot avanzato, SDK Python, marketplace attori | Free tier limitatissimo (~100 pagine/mese), vendor lock-in | €0 (poi ~$49/mese) | Troppo costoso dopo free tier |
| Firecrawl | 500 crediti/mese | API semplice, output LLM-ready, managed | Free tier insufficiente (500 pagine/mese per 30 competitor), rate limiting aggressivo | €0 (poi $19/mese) | Free tier troppo limitato |

**Decisione: Crawl4AI 0.8.x** — L'unica opzione che combina JS rendering, stealth mode, e output LLM-ready a costo zero. Il fatto che sia open source e runni localmente (o su GH Actions) elimina qualsiasi vincolo di quota.

---

## 2. RSS Parsing & News Extraction

| Opzione | Free Tier | Pro | Contro | Costo Mensile | Raccomandazione |
|---------|-----------|-----|--------|---------------|-----------------|
| **newspaper4k + feedparser** | Illimitato (open source) | newspaper4k estrae full article text da URL, feedparser standard RSS/Atom, combo collaudato | newspaper4k può fallire su paywall, manutenzione sporadica | €0 | **RACCOMANDATO** |
| feedparser solo | Illimitato (open source) | Standard de facto RSS, robusto, zero dipendenze | Solo metadata feed, non estrae contenuto articolo | €0 | Insufficiente da solo |
| Trafilatura | Illimitato (open source) | Ottima estrazione contenuto, multi-lingua | Meno diffuso di newspaper4k, API meno intuitiva | €0 | Valida alternativa a newspaper4k |
| NewsAPI | 100 req/giorno | API REST semplice, filtri per sorgente | Free tier solo per sviluppo (non produzione), 100 req/giorno insufficienti | €0 (poi $449/mese) | Proibitivo dopo free tier |

**Decisione: newspaper4k + feedparser** — feedparser per parsing affidabile dei feed RSS, newspaper4k per estrazione full-text degli articoli. Combo collaudato, zero costi, zero limiti.

---

## 3. SERP API (Search Engine Results)

| Opzione | Free Tier | Pro | Contro | Costo Mensile | Raccomandazione |
|---------|-----------|-----|--------|---------------|-----------------|
| **Serper.dev** | 2,500 query/mese | Prezzo più basso del mercato, Google results, JSON pulito, pay-as-you-go dopo free | Solo Google (no Bing), free tier richiede carta di credito | €0 | **RACCOMANDATO** |
| SerpAPI | 100 query/mese | Multi-engine (Google, Bing, YouTube), SDK Python, il più maturo | Free tier troppo piccolo (100/mese), costoso dopo ($50/mese) | €0 (poi $50/mese) | Free tier insufficiente |
| Google Custom Search API | 100 query/giorno | Ufficiale Google, risultati precisi | Setup complesso (CSE ID), 100/giorno = 3000/mese ma rate limiting, no snippet ricchi | €0 | Alternativa gratuita ma setup complesso |
| Brave Search API | 2,000 query/mese | Privacy-first, no tracking, buoni risultati | Meno preciso di Google per query B2B di nicchia, documentazione scarsa | €0 | Buona alternativa, risultati meno rilevanti per AgTech |

**Decisione: Serper.dev** — 2,500 query/mese gratis è più che sufficiente per lo use case (30 query/settimana = ~130/mese). Il margine è enorme. Pay-as-you-go se serve scalare.

---

## 4. LLM (Large Language Model)

| Opzione | Free Tier | Pro | Contro | Costo Mensile | Raccomandazione |
|---------|-----------|-----|--------|---------------|-----------------|
| **Groq (Llama 3.3 70B)** | **1,000 req/giorno**, 30 RPM, 6,000 tokens/min | Inference ultra-veloce (~300 tok/s), JSON mode, tool use, no credit card required | **Free tier ridotto** (era 14,400, ora 1,000 RPD da inizio 2026), 6K TPM può bloccare batch grandi | €0 | **RACCOMANDATO (con cautela)** |
| **Gemini 2.5 Flash** (fallback) | 250 RPD, 1M context | Context window enorme, multimodale, Google backing | Free tier più piccolo (250/giorno), API in evoluzione, latenza variabile | €0 | **RACCOMANDATO come fallback** |
| OpenRouter (vari modelli) | Vari modelli gratuiti | Aggregatore, switch modello senza cambiare codice | Free tier imprevedibile, modelli gratuiti ruotano, latenza variabile | €0 (variabile) | Buon backup ma meno affidabile |
| Ollama locale | Illimitato | Zero latenza rete, privacy totale, nessun rate limit | Richiede GPU/CPU potente (non disponibile su GH Actions), modelli più piccoli | €0 | Non compatibile con GH Actions |
| GPT-4o-mini (OpenAI) | Nessun free tier | Ottima qualità, JSON mode robusto | Nessun free tier, $0.15/1M input tokens | ~€5-15/mese | Budget non compatibile |

**Decisione: Groq (primario) + Gemini 2.5 Flash (fallback)** — Groq resta il più veloce, ma il free tier è stato ridotto drasticamente a inizio 2026: **1,000 req/giorno** (era 14,400), **6,000 tokens/min**, **30 RPM**. Il pipeline stima ~200 req/giorno — ci sta, ma il margine è molto più stretto di quanto indicato inizialmente. Il fallback Gemini è ora **essenziale**, non opzionale.

> **⚠️ IMPATTO CONCRETO:**
> - 1,000 RPD = sufficiente per ~200 req/giorno (classificazione + brief), ma zero margine per retry, test, o scaling
> - 6,000 TPM = collo di bottiglia per batch grandi. Con segnali di ~500 token ciascuno, max ~12 segnali/minuto
> - **Mitigazione:** batch più piccoli (3-5 segnali, non 10), Gemini come fallback attivo (non solo emergenza), considerare Groq Dev tier ($0.10/1K tokens) se il volume cresce
> - **Azione immediata:** verificare limiti correnti su [console.groq.com/settings/limits](https://console.groq.com/settings/limits)

---

## 5. Database

| Opzione | Free Tier | Pro | Contro | Costo Mensile | Raccomandazione |
|---------|-----------|-----|--------|---------------|-----------------|
| **Neon Postgres** | 0.5 GB storage, 100 CU-hours/mese (raddoppiati ott 2025) | Scale-to-zero (risparmia CU-hours), serverless, branching per dev, driver `@neondatabase/serverless` per Vercel edge, acquisita da Databricks (maggio 2025, futuro solido) | 0.5GB stretto con indici GIN pg_trgm (1-3x size dei dati raw), cold start ~1-2s | €0 | **RACCOMANDATO** |
| Supabase | 500 MB, 2 progetti | Postgres + Auth + Realtime + Storage, SDK ricco, dashboard UI | Overkill per questo use case, pause dopo 1 settimana inattività su free tier | €0 | Buona alternativa, troppe feature inutilizzate |
| PlanetScale (Vitess/MySQL) | Free tier rimosso 2024 | — | **Non più disponibile gratis** | $39/mese | Eliminata |
| Railway Postgres | $5 crediti una tantum | Setup veloce, deploy integrato | Crediti esauribili, non sostenibile a lungo termine | €0 (temporaneo) | Non sostenibile |
| SQLite + Turso | 9 GB, 500M rows | Edge-first, embedded, velocissimo in lettura | Meno feature Postgres (no pg_trgm, no JSONB nativo), meno familiare al team | €0 | Alternativa interessante ma meno ecosystem |

**Decisione: Neon Postgres** — Il fondatore l'ha già proposto. Scale-to-zero è ideale per un servizio che processa dati 3x/giorno. CU-hours raddoppiate a 100/mese (ott 2025). pg_trgm e JSONB sono essenziali per fuzzy search e entities.

> **⚠️ Storage budget realistico (0.5GB):** Gli indici GIN con `pg_trgm` possono consumare **1-3x la dimensione dei dati raw**. Con 10K segnali (~20MB dati) + indici GIN su JSONB e trgm, stimare **80-200MB** totali nel primo anno. Ci si sta, ma margine limitato. **Ottimizzazioni:** usare `jsonb_path_ops` (non `jsonb_ops` default) per indici JSONB più compatti, limitare pg_trgm ai soli campi che servono (contacts.full_name, companies.name), archiviare segnali vecchi score <= 2 dopo 90 giorni.

---

## 6. Task Scheduling / Orchestrazione

| Opzione | Free Tier | Pro | Contro | Costo Mensile | Raccomandazione |
|---------|-----------|-----|--------|---------------|-----------------|
| **GitHub Actions cron** | 2,000 min/mese (repo pubblici illimitati) | Zero infra da gestire, secrets management integrato, cron syntax nativa, logs built-in | Max 6 ore per job, cron non garantisce esattezza al minuto, debug più lento | €0 | **RACCOMANDATO** |
| Render cron jobs | 750 ore/mese (web service) | Container Docker, preview environments | Cron jobs richiedono piano paid ($7/mese), free solo per web services | $7/mese | Costo non compatibile |
| Railway | $5 crediti una tantum | Deploy semplice, cron integrato | Crediti esauribili, non free long-term | €0 (temporaneo) | Non sostenibile |
| Vercel cron | Hobby plan | Integrato con Next.js, edge functions | Max 1 invocazione/giorno su free tier, timeout 10s su hobby | €0 | Free tier troppo limitato per pipeline |
| Google Cloud Scheduler + Cloud Run | $0 (300$ crediti trial) | Enterprise-grade, retry logic, dead letter queue | Setup complesso, crediti trial scadono, poi ~$5/mese | €0 (poi ~$5/mese) | Over-engineered per MVP |

**Decisione: GitHub Actions cron** — Il pipeline impiega 5-15 minuti, 3x/giorno. Con Playwright install (~1-2 min/run senza cache), il consumo stimato è **750-1,040 min/mese** (37-52% del free tier da 2,000 min). Secrets management per API keys è integrato. Zero infra da mantenere.

> **⚠️ Mitigazione critica:** cachare Playwright con `actions/cache` (key = versione Playwright) risparmia ~90-180 min/mese. Monitorare il consumo minuti dalla prima settimana via GitHub Settings → Billing. Se il repo è pubblico, i minuti sono illimitati.

---

## 7. Delivery (Notifiche)

### 7a. Delivery Primario

| Opzione | Free Tier | Pro | Contro | Costo Mensile | Raccomandazione |
|---------|-----------|-----|--------|---------------|-----------------|
| **Telegram Bot API** | Illimitato | Zero costo, rich markdown, inline buttons, gruppi, zero setup recipient, fondatore lo preferisce | Richiede Telegram installato, no email trail | €0 | **RACCOMANDATO** |
| Slack Incoming Webhooks | Illimitato | Integrazione team, threading, search | Richiede workspace Slack, meno personale | €0 | Buona alternativa per team più grandi |
| Discord Webhooks | Illimitato | Embed ricchi, gratuito, community-friendly | Meno professionale per B2B, richiede server Discord | €0 | Più adatto a community che B2B |

### 7b. Delivery Backup (Email)

| Opzione | Free Tier | Pro | Contro | Costo Mensile | Raccomandazione |
|---------|-----------|-----|--------|---------------|-----------------|
| **Resend** | 3,000 email/mese, 100/giorno | API moderna, React Email templates, developer-friendly, free tier generoso | 100/giorno limite (sufficiente per brief), dominio personalizzato richiede DNS setup | €0 | **RACCOMANDATO** |
| SendGrid | **Free tier eliminato maggio 2025** | — | Non più gratuito | $19.95/mese | **Eliminata** |
| Mailgun | 1,000 email/mese (primi 3 mesi) | API matura, deliverability alta | Free tier solo 3 mesi, poi $35/mese | €0 (poi $35/mese) | Non sostenibile |
| Amazon SES | $0 (62,000/mese da EC2) | Costo bassissimo, scalabilità infinita | Richiede AWS account, verifica dominio, sandbox mode iniziale, setup complesso | €0 (con EC2) | Over-engineered per MVP |

**Decisione: Telegram (primario) + Resend (fallback email)** — Il fondatore preferisce Telegram per immediatezza. Resend come fallback email per brief archiviabili e condivisibili. Entrambi a costo zero.

---

## 8. Frontend & Hosting

| Opzione | Free Tier | Pro | Contro | Costo Mensile | Raccomandazione |
|---------|-----------|-----|--------|---------------|-----------------|
| **Next.js 14 su Vercel** | 100 GB bandwidth, serverless functions illimitate, 1 progetto commerciale | Native hosting (zero config deploy), API routes serverless, App Router, team ha skills React, edge runtime | Vendor lock-in Vercel, 10s timeout su serverless hobby (sufficiente per read queries) | €0 | **RACCOMANDATO** |
| Remix su Fly.io | 3 shared VMs | Full-stack, nested routes, progressive enhancement | Meno familiarità nel team, setup più complesso | €0 | Buona alternativa se team preferisce |
| SvelteKit su Vercel | Stessi limiti Next.js | Performance superiore, bundle più piccolo, DX eccellente | Team non ha skills Svelte, curva di apprendimento | €0 | Sconsigliato per mancanza competenze team |
| Streamlit | Illimitato (open source) | Python-only, prototyping velocissimo | Non production-grade, UI limitata, no routing, no auth | €0 | Solo per demo Day 1, non per MVP |
| Retool | 5 utenti, app illimitate | Dashboard builder, connessione DB diretta, zero frontend code | Lock-in pesante, customizzazione limitata, 5 utenti max | €0 | Troppo lock-in per progetto formativo |

**Decisione: Next.js 14 su Vercel** — Il team ha competenze React, Vercel offre hosting nativo zero-config, le API routes eliminano il bisogno di un backend separato. `@neondatabase/serverless` driver funziona perfettamente con edge runtime di Vercel.

---

## Riepilogo Raccomandazioni

| Categoria | Scelta | Costo |
|-----------|--------|-------|
| Web Scraping | Crawl4AI 0.8.x | €0 |
| RSS Parsing | newspaper4k + feedparser | €0 |
| SERP API | Serper.dev (2,500/mese) | €0 |
| LLM Primario | Groq — Llama 3.3 70B (1,000 RPD free) | €0 |
| LLM Fallback | Gemini 2.5 Flash | €0 |
| Database | Neon Postgres (0.5GB) | €0 |
| Scheduling | GitHub Actions cron | €0 |
| Delivery Primario | Telegram Bot API | €0 |
| Delivery Backup | Resend (3,000/mese) | €0 |
| Frontend | Next.js 14 su Vercel | €0 |
| NL-to-SQL | Prompt engineering + Groq | €0 |
| Dedup | SHA256 in Postgres | €0 |
| Fuzzy Search | pg_trgm (Postgres ext) | €0 |
| **Totale** | | **€0/mese** |
