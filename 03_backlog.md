# GreenScan — Product Backlog

> 7 Epic, 33 User Stories. Priorità MoSCoW.
> Team: 4 persone (Corrado, Vittorio, Dusan, Tanguy), 3 settimane part-time.
> Budget: €0/mese.

## Legenda

| Simbolo | Significato |
|---------|-------------|
| **M** | Must Have — MVP non funziona senza |
| **S** | Should Have — importante ma non bloccante |
| **C** | Could Have — nice to have |
| **W** | Won't Have (this time) — futuro |
| **XS/S/M/L/XL** | Effort T-shirt sizing |

---

## EP-01: Setup & Infrastructure

> Fondamenta del progetto. Senza questo, niente funziona.

### US-01.1: Repository Setup [M] [S]

**Come** sviluppatore,
**voglio** un repository Git con struttura Python + Next.js,
**così da** avere un ambiente di lavoro pronto per tutto il team.

**Acceptance Criteria:**
- [ ] Repo GitHub creato con `.gitignore` (Python + Node)
- [ ] `pyproject.toml` con dipendenze Python (crawl4ai, feedparser, newspaper4k, asyncpg, groq, python-telegram-bot, resend)
- [ ] `frontend/package.json` con dipendenze Next.js
- [ ] `.env.example` con tutte le variabili necessarie
- [ ] `competitors.yaml` con 3 competitor di test (tier 1)
- [ ] README con setup instructions

**Owner suggerito:** Corrado
**Dipendenze:** Nessuna (primo task)

---

### US-01.2: Neon Database Provisioning [M] [S]

**Come** sviluppatore,
**voglio** un database Neon Postgres configurato con lo schema completo,
**così da** avere il data store pronto per la pipeline.

**Acceptance Criteria:**
- [ ] Progetto Neon creato su free tier
- [ ] Schema 6 tabelle applicato (migration `001_initial.sql`)
- [ ] pg_trgm extension abilitata
- [ ] Connection string salvata come GitHub secret
- [ ] Connessione read-only separata per NL-to-SQL
- [ ] Test connessione da locale OK

**Owner suggerito:** Vittorio
**Dipendenze:** Nessuna

---

### US-01.3: GitHub Actions CI [M] [S]

**Come** sviluppatore,
**voglio** CI con pytest su ogni push,
**così da** non rompere il codice con merge non testati.

**Acceptance Criteria:**
- [ ] `.github/workflows/test.yml` funzionante
- [ ] pytest gira su push e PR
- [ ] Test passa con DB mock/fixture (no connessione Neon in CI)

**Owner suggerito:** Dusan
**Dipendenze:** US-01.1

---

### US-01.4: GitHub Actions Cron Jobs [M] [M]

**Come** operatore,
**voglio** job cron configurati per pipeline giornaliero e settimanale,
**così da** avere scraping automatico senza intervento manuale.

**Acceptance Criteria:**
- [ ] `daily_pipeline.yml`: cron 06:00, 12:00, 18:00 UTC
- [ ] `weekly_deep_scan.yml`: cron domenica 04:00 UTC
- [ ] Tutti i secrets configurati (NEON_DATABASE_URL, GROQ_API_KEY, etc.)
- [ ] `workflow_dispatch` per trigger manuale
- [ ] Playwright chromium installato nel workflow

**Owner suggerito:** Dusan
**Dipendenze:** US-01.1, US-01.2

**Note tecniche:** Playwright necessario per Crawl4AI. Usare cache pip per velocizzare. Timeout 30 min per daily, 45 min per weekly.

---

### US-01.5: Pydantic Configuration [M] [XS]

**Come** sviluppatore,
**voglio** un modulo config centralizzato con validazione,
**così da** gestire env vars in modo type-safe.

**Acceptance Criteria:**
- [ ] `pipeline/config.py` con Pydantic `BaseSettings`
- [ ] Tutte le env vars tipizzate (DATABASE_URL, GROQ_API_KEY, etc.)
- [ ] Valori di default sensati per sviluppo locale
- [ ] Errore chiaro se variabile obbligatoria manca

**Owner suggerito:** Chiunque
**Dipendenze:** US-01.1

---

## EP-02: Data Collection

> Scraping dei competitor da web, RSS e SERP.

### US-02.1: Crawl4AI Web Scraper [M] [L]

**Come** analista,
**voglio** che il sistema scrape-i le pagine web dei competitor,
**così da** avere contenuto aggiornato sulle loro attività.

**Acceptance Criteria:**
- [ ] `pipeline/scraper/web.py` funzionante con Crawl4AI
- [ ] Stealth mode abilitato (anti-bot detection)
- [ ] Async batch: scrape 60-90 pagine in 3-5 minuti
- [ ] Output: `List[RawSignal]` con url, content (markdown), competitor_id, scraped_at
- [ ] Gestione errori: timeout, 403, 404 → log e continua
- [ ] Test con 3 competitor reali

**Owner suggerito:** Tanguy
**Dipendenze:** US-01.1, US-01.5

**Note tecniche:** Crawl4AI usa Playwright internamente. Configurare `browser_config` con headless=True, `crawl_config` con markdown output. Rate limiting: 2 sec tra richieste allo stesso dominio.

---

### US-02.2: RSS Feed Parser [M] [M]

**Come** analista,
**voglio** che il sistema legga i feed RSS dei competitor e delle fonti di settore,
**così da** catturare news e annunci in tempo reale.

**Acceptance Criteria:**
- [ ] `pipeline/scraper/rss.py` con feedparser + newspaper4k
- [ ] Parsing di 30+ feed RSS in < 60 secondi
- [ ] newspaper4k per estrazione full text degli articoli
- [ ] Output: `List[RawSignal]` compatibile con web scraper
- [ ] Gestione feed malformati / offline → log e continua

**Owner suggerito:** Vittorio
**Dipendenze:** US-01.1, US-01.5

---

### US-02.3: Competitor Registry [M] [S]

**Come** analista,
**voglio** un file YAML con tutti i 30 competitor e relative configurazioni,
**così da** aggiungere/rimuovere competitor senza toccare codice.

**Acceptance Criteria:**
- [ ] `competitors.yaml` con schema definito (name, tier, sector, scrape_urls, rss_feeds, serp_queries)
- [ ] `pipeline/scraper/registry.py` che carica e valida il YAML
- [ ] Seed script che popola tabella `competitors` da YAML
- [ ] Validazione: nomi unici, tier 1-3, almeno 1 URL per competitor

**Owner suggerito:** Vittorio
**Dipendenze:** US-01.1, US-01.2

---

### US-02.7: Competitor Research & Data Entry [M] [L]

**Come** team,
**voglio** che i 30 competitor siano effettivamente censiti con URL, RSS feed e SERP queries reali,
**così da** avere dati concreti per il pipeline (non solo uno schema YAML vuoto).

**Acceptance Criteria:**
- [ ] Lista 30 competitor confermata dal fondatore (nomi + tier)
- [ ] Per ogni competitor: almeno 1 newsroom/blog URL verificato
- [ ] Per ogni competitor: RSS feed trovato (o flaggato come assente)
- [ ] Per ogni competitor: 1 SERP query formulata
- [ ] `competitors.yaml` popolato con tutti i 30 competitor
- [ ] Review con fondatore per validazione

**Owner suggerito:** Vittorio + Tanguy (split 15+15)
**Dipendenze:** US-02.3 (schema YAML pronto)

**Note tecniche:** Questo è lavoro di research manuale — non automatizzabile. Il fondatore deve fornire i nomi, il team deve trovare URLs. Parallelizzabile: dividere per tier (Vittorio tier 1-2, Tanguy tier 3). Stimare 1-2 giorni di lavoro effettivo.

---

### US-02.4: SERP Enrichment (Weekly) [S] [M]

**Come** analista,
**voglio** query SERP settimanali per scoprire menzioni competitor non coperte da scraping diretto,
**così da** non perdere notizie pubblicate su siti terzi.

**Acceptance Criteria:**
- [ ] `pipeline/scraper/serp.py` con Serper.dev API
- [ ] 30 query/settimana (1 per competitor), ~1% quota mensile
- [ ] Output: `List[RawSignal]` compatibile con pipeline
- [ ] Dedup automatica vs segnali già raccolti da web/RSS

**Owner suggerito:** Tanguy
**Dipendenze:** US-02.1, US-02.3

---

### US-02.5: Content Deduplication [M] [S]

**Come** sviluppatore,
**voglio** che il sistema elimini contenuti duplicati prima della classificazione,
**così da** non sprecare quote LLM e non inquinare il DB.

**Acceptance Criteria:**
- [ ] `pipeline/enrichment/dedup.py` con SHA256 hashing
- [ ] Batch check vs `signals.content_hash` (UNIQUE index)
- [ ] Drop rate atteso: 40-60% su run successivi
- [ ] Test con contenuti identici e con modifiche minime

**Owner suggerito:** Dusan
**Dipendenze:** US-01.2

---

### US-02.6: Scrape Logging & Health [S] [S]

**Come** operatore,
**voglio** log dettagliati per ogni run di scraping,
**così da** diagnosticare fallimenti e monitorare la salute del sistema.

**Acceptance Criteria:**
- [ ] Ogni run crea entry in `scrape_logs`
- [ ] Traccia: targets total/success/failed, signals new/deduped, duration, errors
- [ ] Status: running → success / partial_failure / failure
- [ ] Query per ultimi 7 run accessibile da API `/api/health`

**Owner suggerito:** Dusan
**Dipendenze:** US-01.2, US-02.1

---

### US-02.8: Pipeline Failure Notification [M] [XS]

**Come** operatore,
**voglio** ricevere un alert Telegram se il pipeline fallisce,
**così da** sapere subito che qualcosa è rotto senza aspettare che il fondatore lo noti.

**Acceptance Criteria:**
- [ ] try/except in `main.py` attorno a `run_daily()` e `run_weekly()`
- [ ] Se eccezione, invio messaggio Telegram con tipo errore e timestamp
- [ ] Il messaggio include quale step ha fallito (scrape, classify, brief, deliver)
- [ ] Test manuale: forzare errore, verificare che alert arriva

**Owner suggerito:** Dusan
**Dipendenze:** US-05.2 (Telegram delivery funzionante)

**Note tecniche:** Letteralmente 5-10 righe di codice. Richiede che il Telegram bot sia già configurato, quindi va in Sprint 2 dopo US-05.2.

---

## EP-03: Signal Processing

> Classificazione LLM e arricchimento entità.

### US-03.1: LLM Client con Fallback [M] [M]

**Come** sviluppatore,
**voglio** un client LLM che usi Groq come primario e Gemini come fallback,
**così da** avere resilienza senza costi.

**Acceptance Criteria:**
- [ ] `pipeline/classifier/llm.py` con client Groq (groq SDK)
- [ ] Fallback automatico a Gemini dopo 3 errori consecutivi
- [ ] Exponential backoff con jitter
- [ ] JSON structured output (response_format)
- [ ] Rate limiting rispettato (Groq: 6,000 tokens/min)
- [ ] Test con mock API

**Owner suggerito:** Corrado
**Dipendenze:** US-01.5

---

### US-03.2: Signal Classification [M] [L]

**Come** analista,
**voglio** che ogni segnale sia classificato automaticamente con categoria, score e summary,
**così da** filtrare il rumore e concentrarmi su ciò che conta.

**Acceptance Criteria:**
- [ ] `pipeline/classifier/categorizer.py` + `scorer.py`
- [ ] Categorie: product_launch, partnership, funding, hiring, expansion, regulatory, technology, market_move, other
- [ ] Relevance score 1-5 con criteri definiti nel prompt
- [ ] Summary: 2-3 frasi in italiano
- [ ] Batch processing: 3-5 segnali per request (Groq free tier: 1,000 RPD, 6K TPM)
- [ ] Prompt in `prompts.py` con few-shot examples
- [ ] Accuracy test manuale su 20 segnali campione: >= 80%

**Owner suggerito:** Corrado
**Dipendenze:** US-03.1

**Note tecniche:** Usare Groq JSON mode (`response_format={"type": "json_object"}`). Il prompt deve includere il contesto del competitor e la definizione di ogni categoria con esempi.

---

### US-03.3: Entity Extraction [M] [M]

**Come** analista,
**voglio** che il sistema estragga entità (aziende, persone, prodotti) da ogni segnale,
**così da** costruire automaticamente il grafo di relazioni.

**Acceptance Criteria:**
- [ ] Estrazione entities come parte della classificazione LLM
- [ ] Output JSON: `{"companies": [...], "people": [...], "products": [...]}`
- [ ] Salvato in `signals.entities_json` (JSONB)
- [ ] Test con segnali contenenti multiple entità

**Owner suggerito:** Corrado
**Dipendenze:** US-03.2

---

### US-03.4: Entity Linking [S] [M]

**Come** analista,
**voglio** che le entità estratte siano collegate a record esistenti in companies/contacts,
**così da** evitare duplicati e costruire profili completi.

**Acceptance Criteria:**
- [ ] `pipeline/enrichment/linker.py` con fuzzy matching pg_trgm
- [ ] Threshold similarity: 0.6 (configurabile)
- [ ] Se match → link a record esistente
- [ ] Se no match → crea nuovo record con confidence 0.5
- [ ] Merge detection: segnala potenziali duplicati per review manuale

**Owner suggerito:** Vittorio
**Dipendenze:** US-03.3, US-01.2

---

## EP-04: CRM & Natural Language Query

> Frontend web e query in linguaggio naturale.

### US-04.1: Next.js Frontend Setup [M] [M]

**Come** utente,
**voglio** un'interfaccia web per navigare competitor, segnali e contatti,
**così da** avere una vista CRM del mio mercato.

**Acceptance Criteria:**
- [ ] Next.js 14 App Router con Tailwind CSS
- [ ] Layout con sidebar navigation (Dashboard, Competitors, Contacts, Signals, Query)
- [ ] Deploy su Vercel (free tier)
- [ ] Connessione a Neon via `@neondatabase/serverless`
- [ ] Responsive design (desktop + tablet)

**Owner suggerito:** Tanguy
**Dipendenze:** US-01.2

---

### US-04.2: Dashboard Page [M] [M]

**Come** fondatore,
**voglio** una dashboard che mostri l'ultimo brief, stats chiave e segnali recenti,
**così da** avere una vista d'insieme in 10 secondi.

**Acceptance Criteria:**
- [ ] Ultimo Battlefield Brief renderizzato (markdown → HTML)
- [ ] Stats cards: segnali oggi, segnali settimana, competitor attivi, score medio
- [ ] Top 5 segnali recenti (score >= 3) con link al dettaglio
- [ ] Stato ultimo run pipeline (da `/api/health`)

**Owner suggerito:** Tanguy
**Dipendenze:** US-04.1, US-05.1

---

### US-04.3: Competitor & Signal Pages [C] [L]

**Come** fondatore,
**voglio** pagine dedicate per competitor (lista + profilo) e segnali (feed filtrabile),
**così da** esplorare in profondità il panorama competitivo.

**Acceptance Criteria:**
- [ ] `/competitors`: tabella con tier badges, settore, conteggio segnali, ricerca
- [ ] `/competitors/:id`: profilo con segnali recenti, contatti, trend (grafico semplice)
- [ ] `/signals`: feed con filtri (competitor, category, score range, date range)
- [ ] Paginazione su tutte le liste

**Owner suggerito:** Tanguy
**Dipendenze:** US-04.1

---

### US-04.4: Contacts Page [C] [M]

**Come** fondatore,
**voglio** una rubrica contatti con ricerca fuzzy e CRUD inline,
**così da** gestire i miei contatti B2B direttamente nel CRM.

**Acceptance Criteria:**
- [ ] Lista contatti con ricerca fuzzy (pg_trgm via API)
- [ ] Filtro per azienda, ruolo, confidence
- [ ] Creazione nuovo contatto (form modale)
- [ ] Edit inline di campi principali
- [ ] Badge confidence (manual vs LLM-extracted)

**Owner suggerito:** Vittorio
**Dipendenze:** US-04.1

---

### US-04.5: Natural Language Query Interface [M] [L]

**Come** fondatore,
**voglio** fare domande al CRM in italiano e ottenere risposte,
**così da** interrogare i dati senza conoscere SQL.

**Acceptance Criteria:**
- [ ] Pagina `/query` con interfaccia chat-like
- [ ] Input: domanda in linguaggio naturale (IT o EN)
- [ ] Processing: schema injection + few-shot → Groq → SQL → risultati → risposta naturale
- [ ] Mostra: risposta naturale + SQL generato (collapsible) + tabella risultati
- [ ] Sicurezza: solo SELECT, read-only connection, timeout 5s, LIMIT 100
- [ ] 10 query di esempio pre-caricate come suggerimenti
- [ ] Test con 20 domande campione: >= 80% risposte corrette

**Owner suggerito:** Corrado + Vittorio
**Dipendenze:** US-04.1, US-03.2 (dati nel DB)

**Note tecniche:** Il prompt NL-to-SQL deve includere: DDL completo delle 6 tabelle, 5-10 few-shot examples con query realistiche, istruzioni per output JSON `{"sql": "...", "explanation": "..."}`. La regex validation deve bloccare qualsiasi statement che non sia SELECT puro.

---

## EP-05: Battlefield Brief

> Generazione e delivery del report giornaliero.

### US-05.1: Brief Generator [M] [M]

**Come** fondatore,
**voglio** un Battlefield Brief giornaliero che sintetizzi i segnali importanti,
**così da** restare aggiornato senza leggere tutto.

**Acceptance Criteria:**
- [ ] `pipeline/brief/generator.py` genera brief markdown
- [ ] Input: segnali del giorno con relevance >= 3
- [ ] Struttura: Executive Summary, segnali per categoria, Key Takeaways, Action Items
- [ ] Generato via Groq con template in `templates.py`
- [ ] Salvato in tabella `briefs`
- [ ] Lunghezza: 500-1500 parole (configurabile)

**Owner suggerito:** Corrado
**Dipendenze:** US-03.2

---

### US-05.2: Telegram Delivery [M] [M]

**Come** fondatore,
**voglio** ricevere il brief su Telegram ogni giorno,
**così da** leggerlo dal telefono appena uscito.

**Acceptance Criteria:**
- [ ] `pipeline/delivery/telegram.py` con python-telegram-bot
- [ ] Brief inviato come messaggio markdown
- [ ] Se brief > 4096 char (limite Telegram), split in messaggi multipli
- [ ] Alert separato per segnali score 5 (critici)
- [ ] Bot token e chat ID configurabili via env vars
- [ ] Test invio manuale OK

**Owner suggerito:** Dusan
**Dipendenze:** US-05.1

---

### US-05.3: Email Delivery (Fallback) [S] [S]

**Come** fondatore,
**voglio** ricevere il brief anche via email come backup,
**così da** avere un archivio email e condividerlo con il team.

**Acceptance Criteria:**
- [ ] `pipeline/delivery/email.py` con Resend SDK
- [ ] Brief convertito in HTML con styling minimale
- [ ] Invio a lista configurabile di destinatari
- [ ] Fallback: se Telegram fallisce, email viene inviata comunque

**Owner suggerito:** Dusan
**Dipendenze:** US-05.1

---

### US-05.4: Brief Archive & Viewer [S] [S]

**Come** fondatore,
**voglio** consultare i brief passati nell'interfaccia web,
**così da** confrontare l'evoluzione nel tempo.

**Acceptance Criteria:**
- [ ] API `/api/briefs` con lista paginata
- [ ] API `/api/briefs/latest` per dashboard
- [ ] Pagina web con lista brief e viewer markdown
- [ ] Ricerca per data

**Owner suggerito:** Tanguy
**Dipendenze:** US-04.1, US-05.1

---

## EP-06: Cross-Signal Correlation (Stretch)

> Analisi avanzata: pattern detection e correlazioni tra segnali. Tutto stretch goal.

### US-06.1: Temporal Correlation [C] [L]

**Come** analista,
**voglio** che il sistema identifichi pattern temporali tra segnali di competitor diversi,
**così da** rilevare trend di settore e mosse coordinate.

**Acceptance Criteria:**
- [ ] `pipeline/brief/correlator.py` analizza segnali ultimi 30 giorni
- [ ] Identifica: cluster temporali (N competitor stessa azione in 7 giorni)
- [ ] Output: sezione "Trend & Correlations" nel brief
- [ ] Minimo 3 correlazioni di esempio funzionanti

**Dipendenze:** US-03.2, US-05.1

---

### US-06.2: Competitive Move Alerts [C] [M]

**Come** fondatore,
**voglio** alert immediati quando un competitor tier 1 fa una mossa significativa,
**così da** reagire in tempo reale.

**Acceptance Criteria:**
- [ ] Trigger: segnale score 5 + competitor tier 1
- [ ] Alert Telegram immediato (non aspetta il brief)
- [ ] Include: competitor, tipo di mossa, summary, link sorgente
- [ ] Max 3 alert/giorno per evitare alert fatigue

**Dipendenze:** US-03.2, US-05.2

---

### US-06.3: Competitor Activity Heatmap [C] [M]

**Come** fondatore,
**voglio** una heatmap che mostri l'attività per competitor nel tempo,
**così da** vedere a colpo d'occhio chi è più attivo.

**Acceptance Criteria:**
- [ ] Componente React heatmap (12 settimane × 30 competitor)
- [ ] Colore basato su volume segnali + score medio
- [ ] Click su cella → drill-down ai segnali specifici
- [ ] Integrato nella dashboard

**Dipendenze:** US-04.1, US-03.2

---

## EP-07: Testing & Handoff

> Quality assurance e documentazione per il handoff al fondatore.

### US-07.1: Unit Tests Pipeline [M] [M]

**Come** sviluppatore,
**voglio** test unitari per ogni modulo della pipeline,
**così da** catturare regressioni prima del deploy.

**Acceptance Criteria:**
- [ ] Test per dedup.py (hash, collision, near-duplicates)
- [ ] Test per classifier (mock LLM, parsing response, error handling)
- [ ] Test per linker (fuzzy match, threshold, new record creation)
- [ ] Test per brief generator (template rendering, empty input)
- [ ] Coverage >= 70% su `pipeline/`
- [ ] Tutti i test passano in CI

**Owner suggerito:** Dusan
**Dipendenze:** EP-02, EP-03

---

### US-07.2: Integration Test — Full Pipeline [M] [L]

**Come** sviluppatore,
**voglio** un test end-to-end che esegua il pipeline completo su 3 competitor di test,
**così da** verificare che tutti i moduli funzionano insieme.

**Acceptance Criteria:**
- [ ] Script `test_e2e.py` che esegue: scrape → dedup → classify → enrich → store → brief → deliver (dry-run)
- [ ] Usa 3 competitor reali ma con rate limiting conservativo
- [ ] Verifica: segnali in DB, brief generato, nessun errore critico
- [ ] Tempo esecuzione < 10 minuti
- [ ] Può girare localmente e in CI (con secrets)
- [ ] **Groq Rate Limit Spike Test:** simulare throttling Groq (mock 429 responses), verificare che il fallback Gemini si attiva correttamente e il pipeline completa senza errori

**Owner suggerito:** Corrado + Dusan
**Dipendenze:** Tutti i moduli EP-02, EP-03, EP-05

---

### US-07.3: Operator Runbook [M] [S]

**Come** fondatore,
**voglio** documentazione operativa per gestire il sistema dopo il handoff,
**così da** essere autonomo nella manutenzione.

**Acceptance Criteria:**
- [ ] Runbook markdown nel repo: come aggiungere competitor, come debuggare pipeline fallita, come fare re-run manuale
- [ ] Guida secrets management (dove sono, come ruotarli)
- [ ] FAQ: "cosa fare se Groq è down", "come leggere scrape_logs", etc.
- [ ] Diagramma architettura aggiornato

**Owner suggerito:** Vittorio
**Dipendenze:** Sistema funzionante

---

### US-07.4: Day 1 Demo [M] [S]

**Come** team,
**voglio** una demo funzionante il primo giorno,
**così da** validare l'architettura end-to-end prima di investire 3 settimane.

**Acceptance Criteria:**
- [ ] Scrape 3 competitor (tier 1) con Crawl4AI
- [ ] Classifica segnali con Groq (categoria + score + summary)
- [ ] Stampa risultati formattati in terminale (tabella o JSON)
- [ ] Tempo totale < 5 minuti
- [ ] Zero dipendenze da frontend o Telegram (solo pipeline Python)

**Owner suggerito:** Tutto il team
**Dipendenze:** US-01.1, US-01.5, US-02.1, US-03.1, US-03.2

**Note tecniche:** Questo è il `run_demo()` in `main.py`. Usa 3 competitor hardcoded, scrive su stdout, non richiede DB. Serve per validare che Crawl4AI + Groq funzionano insieme su GH Actions.

---

## Sprint Planning Suggerito

> Ribilanciato per risolvere: sovraccarico Corrado in Sprint 1, Sprint 3 troppo denso,
> stories mancanti (competitor research, failure notification, rate limit test).

### Sprint 1 (Settimana 1): Fondamenta + Day 1 Demo

| Story | Owner | Effort | Note |
|-------|-------|--------|------|
| US-01.1 Repository Setup | Corrado | S | |
| US-01.2 Neon DB | Vittorio | S | |
| US-01.5 Pydantic Config | Dusan | XS | Spostato da Corrado |
| US-02.1 Crawl4AI Scraper | Tanguy | L | |
| US-02.3 Competitor Registry (schema) | Vittorio | S | Spostato da Corrado |
| US-03.1 LLM Client | Corrado | M | |
| US-02.7 Competitor Research (inizio) | Vittorio + Tanguy | L | Parallelo al setup, serve lista dal fondatore |
| **US-07.4 Day 1 Demo** | **Tutti** | **S** | Corrado integra scraper+LLM |

**Corrado Sprint 1:** S + M + S = bilanciato (prima: S + XS + S + M + L = sovraccarico).
**Cambio chiave:** US-03.2 (Signal Classification, L) spostata a Sprint 2 — la Day 1 Demo usa la classificazione LLM inline nel demo script, la story completa (batch, prompts, few-shot) viene dopo.

**Milestone:** Day 1 Demo funzionante (scrape → classify → stdout). Lista 30 competitor confermata dal fondatore.

### Sprint 2 (Settimana 2): Pipeline Completo + Brief

| Story | Owner | Effort | Note |
|-------|-------|--------|------|
| US-01.3 CI | Dusan | S | |
| US-01.4 Cron Jobs | Dusan | M | Con Playwright caching |
| US-02.2 RSS Parser | Vittorio | M | |
| US-02.5 Dedup | Dusan | S | |
| US-02.7 Competitor Research (fine) | Vittorio + Tanguy | — | Completamento da Sprint 1 |
| US-03.2 Signal Classification | Corrado | L | Spostata da Sprint 1 |
| US-03.3 Entity Extraction | Corrado | M | |
| US-05.1 Brief Generator | Corrado | M | |
| US-05.2 Telegram Delivery | Dusan | M | |
| US-02.8 Pipeline Failure Notification | Dusan | XS | Dopo Telegram delivery |

**Milestone:** Pipeline completo, brief arriva su Telegram. Tutti i 30 competitor nel YAML.

### Sprint 3 (Settimana 3): CRM Frontend + Polish

| Story | Owner | Effort | Note |
|-------|-------|--------|------|
| US-04.1 Next.js Setup | Tanguy | M | |
| US-04.2 Dashboard | Tanguy | M | |
| US-04.5 NL Query Interface | Corrado + Vittorio | L | Must Have core |
| US-03.4 Entity Linking | Vittorio | M | |
| US-02.4 SERP Enrichment | Tanguy | M | |
| US-02.6 Scrape Logging | Dusan | S | |
| US-07.1 Unit Tests | Dusan | M | |
| US-07.2 Integration Test (+ Groq spike test) | Corrado + Dusan | L | Include fallback Gemini test |
| US-07.3 Runbook | Vittorio | S | |

**Milestone:** MVP completo, CRM con dashboard + NL query, tutti i 30 competitor attivi.

### Stretch (se tempo rimane)

| Story | Effort | Priorità |
|-------|--------|----------|
| US-04.3 Competitor & Signal Pages | L | Could Have (declassato da Should) |
| US-04.4 Contacts Page | M | Could Have (declassato da Should) |
| US-05.3 Email Delivery | S | Should Have |
| US-05.4 Brief Archive | S | Should Have |
| US-06.1 Temporal Correlation | L | Could Have |
| US-06.2 Competitive Move Alerts | M | Could Have |
| US-06.3 Activity Heatmap | M | Could Have |

---

## Riepilogo Effort

| Priorità | Stories | Must completare entro |
|----------|---------|----------------------|
| **Must Have** | 23 | Fine settimana 3 |
| **Should Have** | 5 | Fine settimana 3 (se possibile) |
| **Could Have** | 5 | Stretch / fase successiva |
| **Won't Have** | 0 | — |
| **Totale** | **33** | |

> **Note ribilanciamento (da review feedback):**
> - US-04.3 (Competitor & Signal Pages) declassata S → C: Sprint 3 era troppo denso per Tanguy
> - US-04.4 (Contacts Page) declassata S → C: stessa ragione
> - US-02.7 (Competitor Research) aggiunta: blocker non flaggato, serve lavoro manuale
> - US-02.8 (Pipeline Failure Notification) aggiunta: monitoring essenziale
> - US-07.2 integrata con Groq Rate Limit Spike Test
> - Corrado alleggerito in Sprint 1: US-01.5 → Dusan, US-02.3 → Vittorio, US-03.2 → Sprint 2

## Rischi & Mitigazioni

| Rischio | Impatto | Mitigazione |
|---------|---------|-------------|
| **GH Actions minuti** — con Playwright uncached, 3 run/giorno ≈ 750-1,040 min/mese (37-52% free tier) | Pipeline non gira | Cache Playwright (`actions/cache`), monitorare da settimana 1, fallback: repo pubblico (minuti illimitati) |
| **Groq free tier ridotto** — ora 1,000 RPD (era 14,400), 6K TPM, 30 RPM | Classificazione rallentata, quota esaurita con retry | Batch 3-5 segnali, pacing esplicito, Gemini fallback **attivo** (non solo emergenza), routing automatico a Gemini sopra 80% quota |
| **Competitor data entry** — trovare URLs/RSS per 30 aziende è 1-2 giorni di lavoro manuale | Pipeline senza dati | Story US-02.7 dedicata, inizia Sprint 1, split tra 2 persone + fondatore |
| **Neon 0.5GB** — con indici GIN e JSONB, 10K segnali ≈ 100-150MB | DB pieno | Monitorare in `/api/health`, archiviare segnali vecchi score <= 2, piano paid se necessario |
| **Pipeline failure silenziosa** — cron GH Actions fallisce, nessuno se ne accorge | Fondatore senza brief | US-02.8: alert Telegram su failure (XS effort, Sprint 2) |
