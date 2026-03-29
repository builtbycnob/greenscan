-- GreenScan initial schema
-- 6 tables: targets, companies, contacts, signals, briefs, scrape_logs

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Target companies being monitored (Green Growth's ICP)
CREATE TABLE IF NOT EXISTS targets (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    industry        TEXT NOT NULL,
    priority        TEXT NOT NULL DEFAULT 'MEDIUM',
    monitoring      TEXT NOT NULL DEFAULT 'serp_only',
    website         TEXT,
    ticker          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Companies mentioned in signals (superset of targets)
CREATE TABLE IF NOT EXISTS companies (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    website         TEXT,
    industry        TEXT,
    confidence      REAL NOT NULL DEFAULT 0.5,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_companies_name_trgm
    ON companies USING gin (name gin_trgm_ops);

-- People extracted from signals
CREATE TABLE IF NOT EXISTS contacts (
    id              SERIAL PRIMARY KEY,
    full_name       TEXT NOT NULL,
    role            TEXT,
    company_id      INTEGER REFERENCES companies(id),
    confidence      REAL NOT NULL DEFAULT 0.5,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contacts_name_trgm
    ON contacts USING gin (full_name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_contacts_company
    ON contacts (company_id);

-- Classified signals (core data)
CREATE TABLE IF NOT EXISTS signals (
    id              SERIAL PRIMARY KEY,
    url             TEXT NOT NULL,
    title           TEXT,
    content         TEXT,
    content_hash    TEXT NOT NULL UNIQUE,
    source          TEXT NOT NULL,
    category        TEXT,
    relevance_score INTEGER,
    summary         TEXT,
    entities_json   JSONB DEFAULT '{}',
    target_id       INTEGER REFERENCES targets(id),
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    classified_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_signals_content_hash
    ON signals (content_hash);

CREATE INDEX IF NOT EXISTS idx_signals_source_date
    ON signals (source, scraped_at DESC);

CREATE INDEX IF NOT EXISTS idx_signals_category
    ON signals (category);

CREATE INDEX IF NOT EXISTS idx_signals_score
    ON signals (relevance_score DESC);

CREATE INDEX IF NOT EXISTS idx_signals_entities
    ON signals USING gin (entities_json jsonb_path_ops);

CREATE INDEX IF NOT EXISTS idx_signals_scraped_at
    ON signals (scraped_at DESC);

-- Daily briefs archive
CREATE TABLE IF NOT EXISTS briefs (
    id              SERIAL PRIMARY KEY,
    content         TEXT NOT NULL,
    signal_count    INTEGER NOT NULL DEFAULT 0,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_briefs_date
    ON briefs (generated_at DESC);

-- Pipeline run logs
CREATE TABLE IF NOT EXISTS scrape_logs (
    id              SERIAL PRIMARY KEY,
    run_id          TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'running',
    targets_total   INTEGER DEFAULT 0,
    targets_success INTEGER DEFAULT 0,
    targets_failed  INTEGER DEFAULT 0,
    signals_new     INTEGER DEFAULT 0,
    signals_deduped INTEGER DEFAULT 0,
    duration_ms     INTEGER,
    error_message   TEXT,
    metadata        JSONB DEFAULT '{}',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_scrape_logs_date
    ON scrape_logs (started_at DESC);
