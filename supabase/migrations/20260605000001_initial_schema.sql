-- HPI initial schema
-- Follows migration order in DATABASE_SCHEMA.md to satisfy all foreign key constraints

-- ─── Extensions ───────────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;

-- ─── Group 1: Graph ───────────────────────────────────────────────────────────

CREATE TABLE entities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name  TEXT NOT NULL,
    entity_type     TEXT NOT NULL CHECK (entity_type IN (
                        'company', 'security', 'segment', 'program', 'person',
                        'institution', 'gov_agency', 'sector', 'product',
                        'facility', 'geography'
                    )),
    desk            TEXT[] NOT NULL DEFAULT '{}',
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX entities_canonical_name_trgm
    ON entities USING GIN (canonical_name gin_trgm_ops);
CREATE INDEX entities_entity_type
    ON entities (entity_type);
CREATE INDEX entities_desk
    ON entities USING GIN (desk);

CREATE TABLE entity_identifiers (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id   UUID NOT NULL REFERENCES entities(id),
    id_type     TEXT NOT NULL CHECK (id_type IN (
                    'ticker', 'cik', 'figi', 'lei', 'uei',
                    'isin', 'cusip', 'sam_uei', 'duns'
                )),
    id_value    TEXT NOT NULL,
    source      TEXT NOT NULL,
    valid_from  TIMESTAMPTZ NOT NULL,
    valid_to    TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id_type, id_value, valid_from)
);

CREATE INDEX entity_identifiers_entity_id
    ON entity_identifiers (entity_id);
CREATE INDEX entity_identifiers_lookup
    ON entity_identifiers (id_type, id_value)
    WHERE valid_to IS NULL;

CREATE TABLE entity_aliases (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id           UUID NOT NULL REFERENCES entities(id),
    alias               TEXT NOT NULL,
    alias_normalized    TEXT NOT NULL,
    source              TEXT NOT NULL,
    embedding           VECTOR(1536),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (entity_id, alias_normalized)
);

CREATE INDEX entity_aliases_entity_id
    ON entity_aliases (entity_id);
CREATE INDEX entity_aliases_trgm
    ON entity_aliases USING GIN (alias_normalized gin_trgm_ops);
-- ivfflat: effective once sufficient rows exist; no-op queries on empty table are safe
CREATE INDEX entity_aliases_embedding
    ON entity_aliases USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ─── Group 2: Ingestion ───────────────────────────────────────────────────────

CREATE TABLE source_registry (
    id                          TEXT PRIMARY KEY,
    name                        TEXT NOT NULL,
    adapter_class               TEXT NOT NULL,
    desk                        TEXT[] NOT NULL,
    license_class               TEXT NOT NULL CHECK (license_class IN (
                                    'public_domain', 'licensed', 'scrape_gray'
                                )),
    fetch_cron                  TEXT NOT NULL,
    is_active                   BOOLEAN NOT NULL DEFAULT true,
    circuit_breaker_state       TEXT NOT NULL DEFAULT 'closed'
                                    CHECK (circuit_breaker_state IN ('closed', 'open', 'half_open')),
    circuit_breaker_failures    INT NOT NULL DEFAULT 0,
    circuit_breaker_opened_at   TIMESTAMPTZ,
    circuit_breaker_threshold   INT NOT NULL DEFAULT 3,
    rate_limit_per_minute       INT,
    budget_cap_daily_usd        NUMERIC(10, 4),
    last_cursor                 JSONB,
    last_successful_fetch_at    TIMESTAMPTZ,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ingestion_runs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id               TEXT NOT NULL REFERENCES source_registry(id),
    started_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at            TIMESTAMPTZ,
    status                  TEXT NOT NULL DEFAULT 'running'
                                CHECK (status IN ('running', 'success', 'failed', 'skipped')),
    records_fetched         INT NOT NULL DEFAULT 0,
    records_new             INT NOT NULL DEFAULT 0,
    records_duplicate       INT NOT NULL DEFAULT 0,
    error_message           TEXT,
    procrastinate_job_id    BIGINT
);

CREATE INDEX ingestion_runs_source_id
    ON ingestion_runs (source_id, started_at DESC);
CREATE INDEX ingestion_runs_status
    ON ingestion_runs (status, started_at DESC)
    WHERE status IN ('running', 'failed');

CREATE TABLE raw_records (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id           TEXT NOT NULL REFERENCES source_registry(id),
    native_id           TEXT NOT NULL,
    url                 TEXT NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL,
    content_hash        TEXT NOT NULL,
    payload             JSONB,
    payload_url         TEXT,
    payload_size_bytes  INT,
    ingestion_run_id    UUID REFERENCES ingestion_runs(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_id, native_id, content_hash)
);

CREATE INDEX raw_records_source_native
    ON raw_records (source_id, native_id);
CREATE INDEX raw_records_hash
    ON raw_records (content_hash);
CREATE INDEX raw_records_fetched_at
    ON raw_records (fetched_at DESC);

-- entity_edges and resolution_queue come after raw_records (FK dependency)
CREATE TABLE entity_edges (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_entity_id          UUID NOT NULL REFERENCES entities(id),
    to_entity_id            UUID NOT NULL REFERENCES entities(id),
    edge_type               TEXT NOT NULL CHECK (edge_type IN (
                                'HAS_SECURITY', 'FILES_AS', 'REGISTERED_AS',
                                'PARENT_OF', 'RUNS_PROGRAM', 'AWARDED',
                                'SUPPLIES', 'COMPETES_WITH', 'INSIDER_OF',
                                'TRANSACTED', 'HOLDS', 'MEMBER_OF',
                                'PRODUCES', 'EXPOSED_TO', 'OPERATES'
                            )),
    properties              JSONB NOT NULL DEFAULT '{}',
    source_raw_record_id    UUID REFERENCES raw_records(id),
    valid_from              TIMESTAMPTZ NOT NULL,
    valid_to                TIMESTAMPTZ,
    transaction_time        TIMESTAMPTZ NOT NULL DEFAULT now(),
    confidence              FLOAT NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX entity_edges_from
    ON entity_edges (from_entity_id, edge_type)
    WHERE valid_to IS NULL;
CREATE INDEX entity_edges_to
    ON entity_edges (to_entity_id, edge_type)
    WHERE valid_to IS NULL;
CREATE INDEX entity_edges_source_record
    ON entity_edges (source_raw_record_id);

CREATE TABLE resolution_queue (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_mention         TEXT NOT NULL,
    normalized_mention  TEXT NOT NULL,
    context_snippet     TEXT,
    source_id           TEXT NOT NULL,
    raw_record_id       UUID REFERENCES raw_records(id),
    candidates          JSONB NOT NULL DEFAULT '[]',
    confidence          FLOAT NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    status              TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'resolved', 'dismissed', 'new_entity')),
    resolved_entity_id  UUID REFERENCES entities(id),
    resolved_at         TIMESTAMPTZ,
    resolved_by         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX resolution_queue_status
    ON resolution_queue (status, created_at)
    WHERE status = 'pending';

CREATE TABLE normalized_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_record_id   UUID NOT NULL REFERENCES raw_records(id),
    source_id       TEXT NOT NULL,
    record_type     TEXT NOT NULL,
    desk            TEXT[] NOT NULL,
    entity_mentions JSONB NOT NULL DEFAULT '[]',
    structured_data JSONB NOT NULL DEFAULT '{}',
    text_chunk      TEXT,
    embedding       VECTOR(1536),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX normalized_records_raw_record
    ON normalized_records (raw_record_id);
CREATE INDEX normalized_records_source_type
    ON normalized_records (source_id, record_type);
CREATE INDEX normalized_records_embedding
    ON normalized_records USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100)
    WHERE embedding IS NOT NULL;

-- ─── Group 5: Accounts ────────────────────────────────────────────────────────

CREATE TABLE user_profiles (
    id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email       TEXT NOT NULL,
    full_name   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE subscriptions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    stripe_customer_id      TEXT NOT NULL UNIQUE,
    stripe_subscription_id  TEXT UNIQUE,
    tier                    TEXT NOT NULL DEFAULT 'free'
                                CHECK (tier IN ('free', 'pro')),
    status                  TEXT NOT NULL DEFAULT 'active'
                                CHECK (status IN ('active', 'past_due', 'cancelled', 'trialing')),
    current_period_start    TIMESTAMPTZ,
    current_period_end      TIMESTAMPTZ,
    cancelled_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX subscriptions_user_id
    ON subscriptions (user_id);
CREATE INDEX subscriptions_stripe_customer
    ON subscriptions (stripe_customer_id);
CREATE INDEX subscriptions_stripe_subscription
    ON subscriptions (stripe_subscription_id)
    WHERE stripe_subscription_id IS NOT NULL;

CREATE TABLE follows (
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    entity_id   UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, entity_id)
);

CREATE INDEX follows_user_id
    ON follows (user_id);
CREATE INDEX follows_entity_id
    ON follows (entity_id);

-- ─── Group 4: Product ─────────────────────────────────────────────────────────

CREATE TABLE briefs (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    desk                        TEXT NOT NULL CHECK (desk IN ('defense', 'energy', 'ai')),
    date                        DATE NOT NULL,
    status                      TEXT NOT NULL DEFAULT 'pending'
                                    CHECK (status IN ('pending', 'published', 'failed')),
    headline                    TEXT,
    bluf                        TEXT,
    faithfulness_score          FLOAT,
    eval_passed                 BOOLEAN,
    published_at                TIMESTAMPTZ,
    generation_started_at       TIMESTAMPTZ,
    generation_completed_at     TIMESTAMPTZ,
    synthesis_model             TEXT,
    eval_model                  TEXT,
    sources_missing             TEXT[] NOT NULL DEFAULT '{}',
    model_waterfall_metadata    JSONB NOT NULL DEFAULT '{}',
    error_message               TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (desk, date)
);

CREATE INDEX briefs_latest_published
    ON briefs (desk, published_at DESC)
    WHERE status = 'published';
CREATE INDEX briefs_desk_date
    ON briefs (desk, date DESC);

CREATE TABLE brief_items (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brief_id            UUID NOT NULL REFERENCES briefs(id) ON DELETE CASCADE,
    item_type           TEXT NOT NULL CHECK (item_type IN (
                            'award', 'filing', 'policy', 'macro', 'signal'
                        )),
    headline            TEXT NOT NULL,
    body                TEXT NOT NULL,
    entity_ids          UUID[] NOT NULL DEFAULT '{}',
    materiality_score   FLOAT,
    display_order       INT NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX brief_items_brief_id
    ON brief_items (brief_id, display_order);

CREATE TABLE citations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brief_id        UUID NOT NULL REFERENCES briefs(id) ON DELETE CASCADE,
    brief_item_id   UUID REFERENCES brief_items(id) ON DELETE CASCADE,
    raw_record_id   UUID NOT NULL REFERENCES raw_records(id),
    source_id       TEXT NOT NULL,
    url             TEXT NOT NULL,
    fetched_at      TIMESTAMPTZ NOT NULL,
    native_id       TEXT NOT NULL,
    license_class   TEXT NOT NULL CHECK (license_class IN (
                        'public_domain', 'licensed', 'scrape_gray'
                    )),
    title           TEXT,
    excerpt         TEXT,
    entailment_score FLOAT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX citations_brief_id
    ON citations (brief_id);
CREATE INDEX citations_brief_item_id
    ON citations (brief_item_id);

CREATE TABLE calendar_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    desk            TEXT[] NOT NULL,
    event_type      TEXT NOT NULL,
    title           TEXT NOT NULL,
    event_date      DATE NOT NULL,
    event_time_utc  TEXT,
    source_url      TEXT,
    entity_ids      UUID[] NOT NULL DEFAULT '{}',
    is_recurring    BOOLEAN NOT NULL DEFAULT false,
    fetch_triggered BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX calendar_events_date
    ON calendar_events (event_date, event_time_utc);
CREATE INDEX calendar_events_desk
    ON calendar_events USING GIN (desk);

-- ─── Seed: source_registry ────────────────────────────────────────────────────

INSERT INTO source_registry (id, name, adapter_class, desk, license_class, fetch_cron) VALUES
    ('usaspending',   'USAspending.gov',     'USASpendingAdapter',  '{"defense"}', 'public_domain', '0 8 * * *'),
    ('sam_gov',       'SAM.gov',             'SAMGovAdapter',       '{"defense"}', 'public_domain', '30 8 * * *'),
    ('dod_contracts', 'DoD Daily Contracts', 'DoDContractsAdapter', '{"defense"}', 'public_domain', '0 9 * * *'),
    ('edgar',         'SEC EDGAR',           'EDGARAdapter',        '{"defense"}', 'public_domain', '*/30 * * * *'),
    ('congress_gov',  'Congress.gov',        'CongressAdapter',     '{"defense"}', 'public_domain', '0 14 * * *'),
    ('gdelt',         'GDELT',               'GDELTAdapter',        '{"defense"}', 'public_domain', '*/15 * * * *'),
    ('fred',          'FRED',                'FREDAdapter',         '{"defense"}', 'public_domain', '0 15 * * *')
ON CONFLICT (id) DO NOTHING;

-- ─── Auth trigger: auto-create user_profile on sign-up ───────────────────────

CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    INSERT INTO user_profiles (id, email)
    VALUES (NEW.id, NEW.email)
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- ─── Row-level security ───────────────────────────────────────────────────────

ALTER TABLE user_profiles       ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions       ENABLE ROW LEVEL SECURITY;
ALTER TABLE follows             ENABLE ROW LEVEL SECURITY;
ALTER TABLE entities            ENABLE ROW LEVEL SECURITY;
ALTER TABLE entity_edges        ENABLE ROW LEVEL SECURITY;
ALTER TABLE briefs              ENABLE ROW LEVEL SECURITY;
ALTER TABLE brief_items         ENABLE ROW LEVEL SECURITY;
ALTER TABLE citations           ENABLE ROW LEVEL SECURITY;
ALTER TABLE raw_records         ENABLE ROW LEVEL SECURITY;
ALTER TABLE normalized_records  ENABLE ROW LEVEL SECURITY;
ALTER TABLE resolution_queue    ENABLE ROW LEVEL SECURITY;

-- User data — own-row only
CREATE POLICY user_profiles_own ON user_profiles
    USING (id = auth.uid());

CREATE POLICY subscriptions_read_own ON subscriptions
    FOR SELECT USING (user_id = auth.uid());

CREATE POLICY follows_own ON follows
    USING (user_id = auth.uid());

-- Intelligence data — authenticated read
CREATE POLICY entities_auth_read ON entities
    FOR SELECT TO authenticated USING (true);

CREATE POLICY entity_edges_auth_read ON entity_edges
    FOR SELECT TO authenticated USING (true);

CREATE POLICY briefs_auth_read ON briefs
    FOR SELECT TO authenticated USING (status = 'published');

CREATE POLICY brief_items_auth_read ON brief_items
    FOR SELECT TO authenticated USING (true);

CREATE POLICY citations_auth_read ON citations
    FOR SELECT TO authenticated USING (true);

-- Ingestion and admin — deny all direct client access (service role bypasses RLS)
CREATE POLICY raw_records_deny ON raw_records
    USING (false);

CREATE POLICY normalized_records_deny ON normalized_records
    USING (false);

CREATE POLICY resolution_queue_deny ON resolution_queue
    USING (false);

-- ─── Supabase Storage bucket ──────────────────────────────────────────────────

INSERT INTO storage.buckets (id, name, public)
VALUES ('raw-payloads', 'raw-payloads', false)
ON CONFLICT (id) DO NOTHING;
