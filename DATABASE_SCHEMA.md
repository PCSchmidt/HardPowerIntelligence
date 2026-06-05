# Database Schema — Hard Power Intelligence

Postgres schema on Supabase. Five table groups: graph, ingestion, product, accounts,
vectors. Large raw payloads route to Supabase Storage (D005). Bitemporal edges on the
entity graph. Procrastinate owns the job queue schema.

Gate 2 artifact. Pass `BACKEND APPROVED` to close Gate 2 and unlock Gate 4.

---

## Schema overview

| Group | Tables | Purpose |
|-------|--------|---------|
| Graph | `entities`, `entity_identifiers`, `entity_aliases`, `entity_edges`, `resolution_queue` | Entity-resolution graph and crosswalk spine |
| Ingestion | `source_registry`, `ingestion_runs`, `raw_records`, `normalized_records` | Adapter output and provenance |
| Job queue | `procrastinate_*` | Task queue managed by procrastinate |
| Product | `briefs`, `brief_items`, `citations`, `calendar_events` | Published intelligence output |
| Accounts | `user_profiles`, `subscriptions`, `follows` | Users and subscription state |
| Vectors | pgvector columns on `entity_aliases`, `normalized_records` | Semantic search for RAG |

---

## Conventions

- All primary keys: `UUID DEFAULT gen_random_uuid()`
- All timestamps: `TIMESTAMPTZ NOT NULL DEFAULT now()` unless otherwise noted
- `valid_from / valid_to`: bitemporal valid-time axis (null `valid_to` = currently valid)
- `transaction_time`: when the fact was first recorded in this system
- Soft deletes: not used — history is preserved via bitemporal `valid_to` on edges
- Schema: `public` (Supabase default)
- Extensions required: `uuid-ossp`, `pgcrypto`, `pg_trgm`, `vector` (pgvector)

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;
```

---

## Group 1: Graph

### `entities`

Canonical entity registry. One row per real-world entity — company, program, person,
agency, etc. The graph hangs off this table.

```sql
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
```

### `entity_identifiers`

External identifiers for entities. Bitemporal: each identifier is valid for a time
range (`valid_to = null` means currently valid). Handles renames (Raytheon → RTX)
and corporate reorganizations.

```sql
CREATE TABLE entity_identifiers (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id   UUID NOT NULL REFERENCES entities(id),
    id_type     TEXT NOT NULL CHECK (id_type IN (
                    'ticker', 'cik', 'figi', 'lei', 'uei',
                    'isin', 'cusip', 'sam_uei', 'duns'
                )),
    id_value    TEXT NOT NULL,
    source      TEXT NOT NULL,   -- 'sec_tickers', 'openfigi', 'gleif', 'sam_gov'
    valid_from  TIMESTAMPTZ NOT NULL,
    valid_to    TIMESTAMPTZ,     -- null = currently valid
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id_type, id_value, valid_from)
);

CREATE INDEX entity_identifiers_entity_id
    ON entity_identifiers (entity_id);
CREATE INDEX entity_identifiers_lookup
    ON entity_identifiers (id_type, id_value)
    WHERE valid_to IS NULL;        -- deterministic crosswalk lookup, O(1)
```

### `entity_aliases`

All known names for an entity (trade names, former names, abbreviations, ticker symbols
as text). Carries a pgvector embedding for semantic matching when deterministic crosswalk
and trigram matching both fall below the auto-link threshold.

```sql
CREATE TABLE entity_aliases (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id           UUID NOT NULL REFERENCES entities(id),
    alias               TEXT NOT NULL,
    alias_normalized    TEXT NOT NULL,   -- uppercase, stripped (Inc/Corp/LLC removed)
    source              TEXT NOT NULL,   -- where this alias came from
    embedding           VECTOR(1536),    -- text-embedding-3-small (D026); generated at alias creation
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (entity_id, alias_normalized)
);

CREATE INDEX entity_aliases_entity_id
    ON entity_aliases (entity_id);
CREATE INDEX entity_aliases_trgm
    ON entity_aliases USING GIN (alias_normalized gin_trgm_ops);
CREATE INDEX entity_aliases_embedding
    ON entity_aliases USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

### `entity_edges`

Typed, bitemporal, provenance-linked edges. The highest-value edge types for the
Defense desk are `SUPPLIES` (prime → sub-contractor supply chain) and `PARENT_OF`
(corporate structure). Both axes of bitemporal design are present:
- `valid_from / valid_to`: when the relationship was true in the world
- `transaction_time`: when HPI first recorded it

```sql
CREATE TABLE entity_edges (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_entity_id      UUID NOT NULL REFERENCES entities(id),
    to_entity_id        UUID NOT NULL REFERENCES entities(id),
    edge_type           TEXT NOT NULL CHECK (edge_type IN (
                            'HAS_SECURITY', 'FILES_AS', 'REGISTERED_AS',
                            'PARENT_OF', 'RUNS_PROGRAM', 'AWARDED',
                            'SUPPLIES', 'COMPETES_WITH', 'INSIDER_OF',
                            'TRANSACTED', 'HOLDS', 'MEMBER_OF',
                            'PRODUCES', 'EXPOSED_TO', 'OPERATES'
                        )),
    properties          JSONB NOT NULL DEFAULT '{}',  -- amount, program, etc.
    source_raw_record_id UUID REFERENCES raw_records(id),
    valid_from          TIMESTAMPTZ NOT NULL,
    valid_to            TIMESTAMPTZ,    -- null = currently valid
    transaction_time    TIMESTAMPTZ NOT NULL DEFAULT now(),
    confidence          FLOAT NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX entity_edges_from
    ON entity_edges (from_entity_id, edge_type)
    WHERE valid_to IS NULL;
CREATE INDEX entity_edges_to
    ON entity_edges (to_entity_id, edge_type)
    WHERE valid_to IS NULL;
CREATE INDEX entity_edges_source_record
    ON entity_edges (source_raw_record_id);
```

### `resolution_queue`

Entity mentions that could not be resolved automatically (confidence below threshold).
Human operators review via `GET /admin/resolution-queue` and resolve via
`POST /admin/resolution-queue/{id}/resolve` (D015).

```sql
CREATE TABLE resolution_queue (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_mention         TEXT NOT NULL,
    normalized_mention  TEXT NOT NULL,
    context_snippet     TEXT,           -- surrounding text for human context
    source_id           TEXT NOT NULL,
    raw_record_id       UUID REFERENCES raw_records(id),
    candidates          JSONB NOT NULL DEFAULT '[]',
                                        -- [{entity_id, canonical_name, score, match_method}]
    confidence          FLOAT NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    status              TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'resolved', 'dismissed', 'new_entity')),
    resolved_entity_id  UUID REFERENCES entities(id),
    resolved_at         TIMESTAMPTZ,
    resolved_by         TEXT,           -- 'human', 'llm_auto', 'auto_high_confidence'
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX resolution_queue_status
    ON resolution_queue (status, created_at)
    WHERE status = 'pending';
```

---

## Group 2: Ingestion

### `source_registry`

One row per data source. Drives the scheduler's fetch cadence, rate limits, circuit
breaker state, and incremental watermark (cursor). Updated by the worker after each run.

```sql
CREATE TABLE source_registry (
    id                          TEXT PRIMARY KEY,
                                    -- 'usaspending', 'sam_gov', 'dod_contracts', 'edgar', etc.
    name                        TEXT NOT NULL,
    adapter_class               TEXT NOT NULL,  -- Python class e.g. 'USASpendingAdapter'
    desk                        TEXT[] NOT NULL,
    license_class               TEXT NOT NULL CHECK (license_class IN (
                                    'public_domain', 'licensed', 'scrape_gray'
                                )),
    fetch_cron                  TEXT NOT NULL,  -- cron expression (UTC)
    is_active                   BOOLEAN NOT NULL DEFAULT true,

    -- Circuit breaker
    circuit_breaker_state       TEXT NOT NULL DEFAULT 'closed'
                                    CHECK (circuit_breaker_state IN ('closed', 'open', 'half_open')),
    circuit_breaker_failures    INT NOT NULL DEFAULT 0,
    circuit_breaker_opened_at   TIMESTAMPTZ,
    circuit_breaker_threshold   INT NOT NULL DEFAULT 3,  -- failures before open

    -- Rate limiting
    rate_limit_per_minute       INT,        -- null = no limit
    budget_cap_daily_usd        NUMERIC(10, 4),  -- null = no cap

    -- Incremental fetch
    last_cursor                 JSONB,      -- adapter-specific watermark state
    last_successful_fetch_at    TIMESTAMPTZ,

    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Seed rows (Cycle 1 Tier-0 sources):**

```sql
INSERT INTO source_registry (id, name, adapter_class, desk, license_class, fetch_cron) VALUES
    ('usaspending',   'USAspending.gov',     'USASpendingAdapter',   '{"defense"}', 'public_domain', '0 8 * * *'),
    ('sam_gov',       'SAM.gov',             'SAMGovAdapter',        '{"defense"}', 'public_domain', '30 8 * * *'),
    ('dod_contracts', 'DoD Daily Contracts', 'DoDContractsAdapter',  '{"defense"}', 'public_domain', '0 9 * * *'),
    ('edgar',         'SEC EDGAR',           'EDGARAdapter',         '{"defense"}', 'public_domain', '*/30 * * * *'),
    ('congress_gov',  'Congress.gov',        'CongressAdapter',      '{"defense"}', 'public_domain', '0 14 * * *'),
    ('gdelt',         'GDELT',               'GDELTAdapter',         '{"defense"}', 'public_domain', '*/15 * * * *'),
    ('fred',          'FRED',                'FREDAdapter',          '{"defense"}', 'public_domain', '0 15 * * *')
ON CONFLICT (id) DO NOTHING;
```

---

### `ingestion_runs`

Audit log for every adapter execution. One row per fetch attempt. Provides the
data-freshness signal for the brief staleness indicator (D013).

```sql
CREATE TABLE ingestion_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id           TEXT NOT NULL REFERENCES source_registry(id),
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    status              TEXT NOT NULL DEFAULT 'running'
                            CHECK (status IN ('running', 'success', 'failed', 'skipped')),
    records_fetched     INT NOT NULL DEFAULT 0,
    records_new         INT NOT NULL DEFAULT 0,
    records_duplicate   INT NOT NULL DEFAULT 0,
    error_message       TEXT,
    procrastinate_job_id BIGINT       -- procrastinate_jobs.id for correlation
);

CREATE INDEX ingestion_runs_source_id
    ON ingestion_runs (source_id, started_at DESC);
CREATE INDEX ingestion_runs_status
    ON ingestion_runs (status, started_at DESC)
    WHERE status IN ('running', 'failed');
```

---

### `raw_records`

Immutable, append-only record of every raw payload fetched from a source. Provenance
by construction: every row carries `url`, `fetched_at`, and `content_hash` (D008).

Large payloads (EDGAR filings, bulk downloads — typically 1–5MB) are routed to
Supabase Storage and referenced via `payload_url`. Small structured payloads (<50KB)
are stored inline in `payload` (D005).

Dedup key: `(source_id, native_id, content_hash)`.

```sql
CREATE TABLE raw_records (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id           TEXT NOT NULL REFERENCES source_registry(id),
    native_id           TEXT NOT NULL,      -- source's own identifier for this record
    url                 TEXT NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL,
    content_hash        TEXT NOT NULL,      -- SHA-256 of raw payload bytes
    payload             JSONB,              -- inline for small payloads (<50KB)
    payload_url         TEXT,               -- Supabase Storage path for large payloads
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
```

**Payload routing rule** (enforced in adapter base class):
- `payload_size_bytes > 50_000` → store in Supabase Storage under
  `raw-payloads/{source_id}/{year}/{month}/{native_id}.json`, set `payload_url`, leave `payload = null`
- `payload_size_bytes <= 50_000` → store inline in `payload`, leave `payload_url = null`

---

### `normalized_records`

Parsed, structured output from each adapter's `parse()` step. One raw record may
produce multiple normalized records (e.g., one EDGAR filing produces one 8-K record per
item). Carries entity mentions for the resolution pipeline and a text chunk for pgvector
indexing.

```sql
CREATE TABLE normalized_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_record_id   UUID NOT NULL REFERENCES raw_records(id),
    source_id       TEXT NOT NULL,
    record_type     TEXT NOT NULL,
                        -- 'contract_award', 'filing_8k', 'filing_10k', 'filing_form4',
                        -- 'sam_entity', 'congress_bill', 'news_item', etc.
    desk            TEXT[] NOT NULL,
    entity_mentions JSONB NOT NULL DEFAULT '[]',
                        -- [{mention, normalized, entity_id, confidence, resolved_by}]
    structured_data JSONB NOT NULL DEFAULT '{}',
                        -- record-type-specific fields (award amount, filing date, etc.)
    text_chunk      TEXT,       -- free text for pgvector indexing (RAG passages)
    embedding       VECTOR(1536),   -- text-embedding-3-small (D026); generated post-ingestion async
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
```

---

## Group 3: Job Queue (procrastinate)

Procrastinate creates and manages its own schema via migrations. Do not create these
tables manually — run `procrastinate schema --apply` during deployment.

**Tables created by procrastinate:**

| Table | Purpose |
|-------|---------|
| `procrastinate_jobs` | Job queue; workers claim via `SELECT ... FOR UPDATE SKIP LOCKED` |
| `procrastinate_events` | Job lifecycle events (scheduled, started, succeeded, failed) |
| `procrastinate_periodic_defers` | Tracks last defer time for periodic tasks |

**Scheduling integration (procrastinate PeriodicTask — D026):**

Job scheduling is owned by procrastinate's native `@app.periodic` decorator, not
`pg_cron`. The `hpi-worker` process registers all periodic tasks in code; state is
stored in `procrastinate_periodic_defers`. No `pg_cron` extension required — this
works on Supabase Free tier.

Task registration lives in `worker/tasks.py`:

```python
@app.periodic(cron="0 10 * * *")    # USAspending: 8am UTC daily
async def fetch_usaspending(timestamp: int) -> None: ...

@app.periodic(cron="30 8 * * *")    # SAM.gov: 8:30am UTC
async def fetch_sam_gov(timestamp: int) -> None: ...

@app.periodic(cron="30 10 * * *")   # Brief generation: 5:30am ET = 10:30 UTC (D014)
async def generate_defense_brief(timestamp: int) -> None: ...
```

Each task reads its source config from `source_registry` at runtime. The
`source_registry.fetch_cron` column documents the intended cadence but is not
consumed by pg_cron — it is the reference value used when registering the
`@app.periodic` decorator and for display in the admin status endpoint.

---

## Group 4: Product

### `briefs`

One row per desk per calendar day. Tracks the full lifecycle: `pending` → `published`
(or `failed` with fallback to previous published brief per D013).

```sql
CREATE TABLE briefs (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    desk                        TEXT NOT NULL CHECK (desk IN ('defense', 'energy', 'ai')),
    date                        DATE NOT NULL,
    status                      TEXT NOT NULL DEFAULT 'pending'
                                    CHECK (status IN ('pending', 'published', 'failed')),
    headline                    TEXT,
    bluf                        TEXT,           -- 2–3 sentence BLUF summary
    faithfulness_score          FLOAT,          -- eval gate score (0–1)
    eval_passed                 BOOLEAN,
    published_at                TIMESTAMPTZ,
    generation_started_at       TIMESTAMPTZ,
    generation_completed_at     TIMESTAMPTZ,
    synthesis_model             TEXT,           -- pinned model ID used
    eval_model                  TEXT,
    sources_missing             TEXT[] NOT NULL DEFAULT '{}',
    model_waterfall_metadata    JSONB NOT NULL DEFAULT '{}',
    error_message               TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (desk, date)
);

-- Critical index for D013 fallback: "latest published brief for this desk"
CREATE INDEX briefs_latest_published
    ON briefs (desk, published_at DESC)
    WHERE status = 'published';

CREATE INDEX briefs_desk_date
    ON briefs (desk, date DESC);
```

**D013 fallback query pattern:**

```sql
-- Returns the most recently published brief for a desk (regardless of date)
SELECT * FROM briefs
WHERE desk = 'defense' AND status = 'published'
ORDER BY published_at DESC
LIMIT 1;
```

---

### `brief_items`

Individual story items within a brief. Ordered by `display_order`.

```sql
CREATE TABLE brief_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brief_id        UUID NOT NULL REFERENCES briefs(id) ON DELETE CASCADE,
    item_type       TEXT NOT NULL CHECK (item_type IN (
                        'award', 'filing', 'policy', 'macro', 'signal'
                    )),
    headline        TEXT NOT NULL,
    body            TEXT NOT NULL,
    entity_ids      UUID[] NOT NULL DEFAULT '{}',
    materiality_score FLOAT,
    display_order   INT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX brief_items_brief_id
    ON brief_items (brief_id, display_order);
```

### `citations`

Source citations for brief items. Every claim in a published brief links to a citation
row, which links back to the originating `raw_record`. The entailment score from the
eval gate is stored here.

```sql
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
    excerpt         TEXT,       -- short quote; never full text for scrape_gray
    entailment_score FLOAT,     -- claim-source entailment from eval gate (0–1)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX citations_brief_id
    ON citations (brief_id);
CREATE INDEX citations_brief_item_id
    ON citations (brief_item_id);
```

### `calendar_events`

Scheduled catalyst events that drive the fetch calendar and power the user-facing
catalyst calendar widget (SPEC: Web — Defense Desk Reader).

```sql
CREATE TABLE calendar_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    desk            TEXT[] NOT NULL,
    event_type      TEXT NOT NULL,
                        -- 'ndaa_markup', 'earnings', 'fomc', 'cpi', 'jobs_report',
                        -- 'dsca_notification', 'contract_deadline', 'recess', etc.
    title           TEXT NOT NULL,
    event_date      DATE NOT NULL,
    event_time_utc  TEXT,       -- HH:MM for timed releases (CPI = '13:30', FOMC = '19:00')
    source_url      TEXT,
    entity_ids      UUID[] NOT NULL DEFAULT '{}',
    is_recurring    BOOLEAN NOT NULL DEFAULT false,
    fetch_triggered BOOLEAN NOT NULL DEFAULT false,  -- true once intraday fetch fired
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX calendar_events_date
    ON calendar_events (event_date, event_time_utc);
CREATE INDEX calendar_events_desk
    ON calendar_events USING GIN (desk);
```

---

## Group 5: Accounts

### `user_profiles`

Extends Supabase `auth.users`. Created automatically via Supabase Auth trigger on
user sign-up.

```sql
CREATE TABLE user_profiles (
    id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email       TEXT NOT NULL,
    full_name   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Trigger to create profile on sign-up:**

```sql
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
```

---

### `subscriptions`

Source of truth for subscription state. Updated exclusively by Stripe webhook handlers
in `hpi-api` (D012). Never written by Next.js or by Supabase client-side calls.

```sql
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
    ON subscriptions (user_id);     -- one subscription row per user
CREATE INDEX subscriptions_stripe_customer
    ON subscriptions (stripe_customer_id);
CREATE INDEX subscriptions_stripe_subscription
    ON subscriptions (stripe_subscription_id)
    WHERE stripe_subscription_id IS NOT NULL;
```

---

### `follows`

User-to-entity follows. Powers the "followed entities" filter on the brief reader.
Pro tier only (enforced at API layer).

```sql
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
```

---

## Row-level security

Enable RLS on all tables. `hpi-api` connects with the service role key (bypasses RLS).
RLS protects against any direct Supabase client access that bypasses the API layer.

```sql
ALTER TABLE user_profiles    ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions    ENABLE ROW LEVEL SECURITY;
ALTER TABLE follows          ENABLE ROW LEVEL SECURITY;
ALTER TABLE entities         ENABLE ROW LEVEL SECURITY;
ALTER TABLE entity_edges     ENABLE ROW LEVEL SECURITY;
ALTER TABLE briefs           ENABLE ROW LEVEL SECURITY;
ALTER TABLE brief_items      ENABLE ROW LEVEL SECURITY;
ALTER TABLE citations        ENABLE ROW LEVEL SECURITY;
ALTER TABLE raw_records      ENABLE ROW LEVEL SECURITY;
ALTER TABLE normalized_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE resolution_queue ENABLE ROW LEVEL SECURITY;
```

### User data — own-row-only

```sql
-- user_profiles: read and update own profile only
CREATE POLICY user_profiles_own ON user_profiles
    USING (id = auth.uid());

-- subscriptions: read own subscription; no direct writes (service role only)
CREATE POLICY subscriptions_read_own ON subscriptions
    FOR SELECT USING (user_id = auth.uid());

-- follows: read and write own follows
CREATE POLICY follows_own ON follows
    USING (user_id = auth.uid());
```

### Public intelligence data — authenticated read

Briefs and entities are readable by any authenticated user. Content gating (free vs. pro)
is enforced at the API layer, not in RLS — RLS would create complex policy logic that
mirrors business rules better kept in FastAPI.

```sql
-- Authenticated read on public intelligence tables
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
```

### Ingestion and admin tables — service role only

No direct client access:

```sql
-- Deny all for anon and authenticated; service role bypasses RLS
CREATE POLICY raw_records_deny ON raw_records
    USING (false);

CREATE POLICY normalized_records_deny ON normalized_records
    USING (false);

CREATE POLICY resolution_queue_deny ON resolution_queue
    USING (false);
```

---

## Supabase Storage

Bucket: `raw-payloads`  
Access: private (service role only — never exposed to client)

**Path convention:**
```
raw-payloads/{source_id}/{YYYY}/{MM}/{native_id_sanitized}.json
```

Example:
```
raw-payloads/edgar/2026/06/0000936468-26-000042.json
```

Files are uploaded by the `hpi-worker` adapter during ingestion. `raw_records.payload_url`
stores the Supabase Storage path (not a public URL). The `hpi-api` reads large payloads
from Storage via the service role client when needed for RAG context.

Lifecycle policy: retain indefinitely at MVP (storage cost is negligible vs. value of
raw provenance). Re-evaluate at 10GB+ storage usage.

---

## Indexes summary

| Table | Index | Type | Columns | Notes |
|-------|-------|------|---------|-------|
| `entities` | `entities_canonical_name_trgm` | GIN trgm | `canonical_name` | Fuzzy entity search |
| `entity_identifiers` | `entity_identifiers_lookup` | B-tree | `(id_type, id_value)` WHERE `valid_to IS NULL` | O(1) crosswalk |
| `entity_aliases` | `entity_aliases_trgm` | GIN trgm | `alias_normalized` | Fuzzy alias match |
| `entity_aliases` | `entity_aliases_embedding` | ivfflat | `embedding` | Semantic fallback |
| `entity_edges` | `entity_edges_from` | B-tree | `(from_entity_id, edge_type)` WHERE `valid_to IS NULL` | Forward traversal |
| `entity_edges` | `entity_edges_to` | B-tree | `(to_entity_id, edge_type)` WHERE `valid_to IS NULL` | Reverse traversal |
| `raw_records` | `raw_records_source_native` | B-tree | `(source_id, native_id)` | Dedup check |
| `raw_records` | `raw_records_hash` | B-tree | `content_hash` | Hash dedup |
| `normalized_records` | `normalized_records_embedding` | ivfflat | `embedding` WHERE NOT NULL | RAG vector search |
| `briefs` | `briefs_latest_published` | B-tree | `(desk, published_at DESC)` WHERE `published` | D013 fallback |
| `resolution_queue` | `resolution_queue_status` | B-tree | `(status, created_at)` WHERE `pending` | Admin review queue |
| `subscriptions` | `subscriptions_user_id` | unique B-tree | `user_id` | Auth middleware lookup |

---

## Migration order

Foreign key constraints require this creation order:

1. `entities`
2. `entity_identifiers`, `entity_aliases`
3. `source_registry`
4. `ingestion_runs`
5. `raw_records` (references `ingestion_runs`, `source_registry`)
6. `entity_edges` (references `entities`, `raw_records`)
7. `resolution_queue` (references `raw_records`, `entities`)
8. `normalized_records` (references `raw_records`)
9. `user_profiles`, `subscriptions`, `follows`
10. `briefs`
11. `brief_items` (references `briefs`)
12. `citations` (references `briefs`, `brief_items`, `raw_records`)
13. `calendar_events`
14. Procrastinate schema: `procrastinate schema --apply`
15. pg_cron schedules

---

## Key query patterns

### D013 fallback: latest published brief

```sql
SELECT * FROM briefs
WHERE desk = $1 AND status = 'published'
ORDER BY published_at DESC
LIMIT 1;
```

### Deterministic crosswalk lookup

```sql
SELECT e.id, e.canonical_name, e.entity_type
FROM entity_identifiers ei
JOIN entities e ON e.id = ei.entity_id
WHERE ei.id_type = $1    -- e.g. 'ticker'
  AND ei.id_value = $2   -- e.g. 'LMT'
  AND ei.valid_to IS NULL;
```

### Entity graph traversal (1-hop, e.g. all programs run by a company)

```sql
SELECT e.id, e.canonical_name, e.entity_type, ee.edge_type, ee.properties
FROM entity_edges ee
JOIN entities e ON e.id = ee.to_entity_id
WHERE ee.from_entity_id = $1
  AND ee.edge_type = 'RUNS_PROGRAM'
  AND ee.valid_to IS NULL;
```

### RAG: find relevant passages for brief generation

```sql
SELECT nr.id, nr.text_chunk, nr.source_id, nr.structured_data,
       rr.url, rr.fetched_at, rr.native_id,
       1 - (nr.embedding <=> $1::vector) AS cosine_similarity
FROM normalized_records nr
JOIN raw_records rr ON rr.id = nr.raw_record_id
WHERE nr.embedding IS NOT NULL
  AND rr.fetched_at > now() - INTERVAL '48 hours'
ORDER BY nr.embedding <=> $1::vector
LIMIT 20;
```

### Subscription tier check (auth middleware)

```sql
SELECT tier, status FROM subscriptions
WHERE user_id = $1
LIMIT 1;
```
