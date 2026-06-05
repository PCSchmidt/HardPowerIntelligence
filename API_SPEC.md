# API Specification — Hard Power Intelligence

Backend service: `hpi-api` (FastAPI on Fly.io). Per D011, Next.js never calls Supabase
directly for application data — all data fetching routes through these endpoints.

Gate 2 artifact. Pass `BACKEND APPROVED` to close Gate 2 and unlock Gate 4.

---

## Conventions

| Property | Value |
|----------|-------|
| Base URL | `https://api.hardpowerintel.com/v1` |
| Protocol | HTTPS only |
| Auth | `Authorization: Bearer <supabase-jwt>` on all protected routes |
| Request body | `application/json` |
| Response body | `application/json` |
| Datetimes | ISO 8601 UTC strings (`2026-06-05T09:35:00Z`) |
| Dates | ISO 8601 date strings (`2026-06-05`) |
| Pagination | Cursor-based: `cursor` query param → `next_cursor` in response |
| Empty list | `[]`, never `null` |
| UUIDs | `string` format, lowercase hyphenated |

---

## Middleware stack

Middleware runs in this order on every request (except explicitly exempted routes):

### 1. Auth middleware

Applies to: all routes except `GET /health`, `POST /stripe/webhook`.

FastAPI reads the `Authorization: Bearer <jwt>` header and verifies the Supabase JWT
locally using `SUPABASE_JWT_SECRET` (no round-trip to Supabase). On success, attaches
to request state:

```
state.user_id   # UUID from JWT sub claim
state.email     # string
state.is_admin  # bool, from JWT custom claim is_admin (default false)
```

Failure responses:
- Missing header → `401 {"error": {"code": "missing_token", "message": "Authorization header required"}}`
- Invalid/expired JWT → `401 {"error": {"code": "invalid_token", "message": "Token invalid or expired"}}`

### 2. Subscription tier middleware

Applies to: all auth-required routes.

Reads `subscriptions` table for `state.user_id`. Attaches `state.tier: "free" | "pro"`.
Users with no subscription row are treated as `free`.

Pro-only routes return `403` for free-tier users:
```json
{"error": {"code": "pro_required", "message": "Pro subscription required for this resource"}}
```

### 3. Admin middleware

Applies to: all `/admin/*` routes.

Checks `state.is_admin`. Returns `403` if false:
```json
{"error": {"code": "admin_required", "message": "Admin access required"}}
```

---

## Error schema

All error responses use this envelope:

```json
{
  "error": {
    "code": "string",
    "message": "string",
    "details": {}
  }
}
```

| HTTP status | Meaning |
|-------------|---------|
| `400` | Bad request (invalid query params, malformed body) |
| `401` | Missing or invalid JWT |
| `403` | Valid JWT but insufficient tier or missing admin claim |
| `404` | Resource not found |
| `422` | Validation error (FastAPI/Pydantic default) |
| `500` | Internal server error (always reported to Sentry) |

---

## Subscription tiers

| Feature | Free | Pro |
|---------|------|-----|
| Daily brief — current day, full content | ✓ | ✓ |
| Brief archive — rolling 90 days | — | ✓ |
| Entity 360 pages | — | ✓ |
| PDF export | — | ✓ |
| Follows / personalization | — | ✓ |
| Additional desks (Cycle 2) | — | ✓ |

Both tiers receive the full daily brief for the current day. Pro adds archive access,
entity 360, PDF, and follows. New subscribers get a 14-day Pro trial (CC required, D019).
All gating is enforced at the FastAPI layer (D012) — never rely solely on Next.js middleware.

---

## Endpoints

---

### Health

#### `GET /health`

No auth required. Used by Fly.io health checks.

**Response `200`:**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "timestamp": "2026-06-05T09:35:00Z"
}
```

---

### Briefs

#### `GET /briefs`

Returns a paginated list of published briefs for a desk, latest first.

**Auth:** required  
**Tier gating:** free users see only the current day's brief; pro users see rolling 90-day archive

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `desk` | `"defense" \| "energy" \| "ai"` | required | Desk to query |
| `limit` | `int` | `20` | Max results (max 50) |
| `cursor` | `string` | — | Pagination cursor from previous response |

**Response `200`:**
```json
{
  "briefs": [
    {
      "id": "uuid",
      "desk": "defense",
      "date": "2026-06-05",
      "status": "published",
      "published_at": "2026-06-05T09:35:00Z",
      "headline": "DoD Awards $4.2B in LRASM Production Contracts; RTX Wins IBCS Follow-On",
      "bluf": "Three major procurement decisions today signal accelerating...",
      "faithfulness_score": 0.97
    }
  ],
  "next_cursor": "string | null"
}
```

Note: `bluf` is a short summary (2–3 sentences). Full `items` and `citations` arrays are
not returned in the list view — use `GET /briefs/{id}` for full content.

---

#### `GET /briefs/latest`

Returns the most recently published brief for a desk. Implements D013 fallback: if the
latest brief is `pending` or `failed`, returns the last `published` brief with a
staleness indicator.

**Auth:** required  
**Tier gating:** both tiers receive full content for the current day's brief; Pro additionally unlocks archive access via `GET /briefs/{id}` and `GET /briefs`

**Query params:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `desk` | `"defense"` | yes | Desk to query |

**Response `200`:**
```json
{
  "id": "uuid",
  "desk": "defense",
  "date": "2026-06-05",
  "status": "published",
  "published_at": "2026-06-05T09:35:00Z",
  "headline": "...",
  "bluf": "...",
  "faithfulness_score": 0.97,
  "staleness_indicator": null,
  "items": [
    {
      "id": "uuid",
      "item_type": "award",
      "headline": "Lockheed Martin Awarded $1.1B LRASM Production Contract",
      "body": "The Navy awarded Lockheed Martin a...",
      "entity_ids": ["uuid-lmt", "uuid-navy"],
      "citation_ids": ["uuid-cit-1", "uuid-cit-2"],
      "materiality_score": 0.91,
      "display_order": 1
    }
  ],
  "citations": [
    {
      "id": "uuid-cit-1",
      "source_id": "usaspending",
      "url": "https://www.usaspending.gov/award/CONT_AWD_...",
      "fetched_at": "2026-06-05T04:15:00Z",
      "native_id": "CONT_AWD_N0001926C0042",
      "license_class": "public_domain",
      "title": "N00019-26-C-0042 Lockheed Martin",
      "excerpt": "Award amount: $1,100,000,000; Description: Long Range Anti-Ship Missile..."
    }
  ],
  "sources_missing": [],
  "model_waterfall": {
    "synthesis_model": "deepseek/deepseek-v4-pro",
    "eval_model": "qwen/qwen3.7-max",
    "eval_passed": true
  }
}
```

**Staleness indicator (D013 fallback — when returned brief is not today's):**
```json
{
  "staleness_indicator": {
    "last_updated": "2026-06-05T09:35:00Z",
    "current_status": "pending",
    "message": "Today's brief is being generated. Showing last published brief."
  }
}
```

---

#### `GET /briefs/{id}`

Returns a single brief by ID with full content.

**Auth:** required  
**Tier gating:** free users can access today's brief by ID with full content; any brief with `date < today` requires Pro and returns `403` for free-tier users

**Path params:** `id: UUID`

**Response `200`:** same shape as `GET /briefs/latest` pro response above.

**Response `404`:**
```json
{"error": {"code": "not_found", "message": "Brief not found"}}
```

---

#### `GET /briefs/{id}/pdf`

Returns a PDF rendering of the brief.

**Auth:** required  
**Tier gating:** pro only

Generates on demand via WeasyPrint (pure Python, D017). Cached in Supabase Storage after
first generation. Response is streamed.

**Response `200`:** `Content-Type: application/pdf`

**Response `403`:**
```json
{"error": {"code": "pro_required", "message": "PDF export requires a Pro subscription"}}
```

---

### Entities

#### `GET /entities/search`

Fuzzy search for entities by name. Used for autocomplete in the follows UI and entity
360 navigation.

**Auth:** required  
**Tier gating:** all tiers

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `q` | `string` | required | Search query (min 2 chars) |
| `limit` | `int` | `10` | Max results (max 25) |
| `desk` | `string` | — | Filter by desk (`defense`, `energy`, `ai`) |

Uses `pg_trgm` fuzzy match on `entity_aliases.alias_normalized`. Falls back to
pgvector semantic search for queries with low trigram similarity.

**Response `200`:**
```json
{
  "entities": [
    {
      "id": "uuid",
      "canonical_name": "Lockheed Martin Corporation",
      "entity_type": "company",
      "ticker": "LMT",
      "desk": ["defense"]
    }
  ]
}
```

---

#### `GET /entities/{id}`

Returns the Entity 360 view for a canonical entity.

**Auth:** required  
**Tier gating:** pro only

**Path params:** `id: UUID`

**Response `200`:**
```json
{
  "id": "uuid",
  "canonical_name": "Lockheed Martin Corporation",
  "entity_type": "company",
  "desk": ["defense"],
  "identifiers": {
    "ticker": "LMT",
    "cik": "936468",
    "figi": "BBG000C1BW00",
    "lei": "549300M7SY5VLQJBSD64",
    "uei": "9C6ZVVD59DU4"
  },
  "aliases": ["Lockheed Martin", "LMT", "Lockheed"],
  "recent_awards": [
    {
      "award_id": "CONT_AWD_...",
      "amount_usd": 1100000000,
      "description": "LRASM Production",
      "award_date": "2026-06-05",
      "contracting_office": "NAVAIR"
    }
  ],
  "recent_filings": [
    {
      "form_type": "8-K",
      "filed_at": "2026-06-03",
      "description": "Lockheed Martin Reports Q1 2026 Results",
      "url": "https://www.sec.gov/Archives/edgar/..."
    }
  ],
  "recent_insider_transactions": [
    {
      "form_type": "Form 4",
      "insider_name": "James Taiclet",
      "transaction_type": "Purchase",
      "shares": 5000,
      "price_per_share": 465.50,
      "transaction_date": "2026-05-15"
    }
  ],
  "related_programs": ["F-35", "LRASM", "Sikorsky Black Hawk"],
  "edges": [
    {
      "edge_type": "PARENT_OF",
      "direction": "from",
      "related_entity_id": "uuid",
      "related_entity_name": "Sikorsky Aircraft Corporation"
    }
  ]
}
```

**Response `404`:**
```json
{"error": {"code": "not_found", "message": "Entity not found"}}
```

---

### Calendar

#### `GET /calendar`

Returns upcoming catalyst events.

**Auth:** required  
**Tier gating:** all tiers

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `desk` | `string` | — | Filter by desk |
| `from` | `date` | today | Start date (ISO 8601) |
| `to` | `date` | today + 30 days | End date (ISO 8601) |
| `limit` | `int` | `50` | Max results |

**Response `200`:**
```json
{
  "events": [
    {
      "id": "uuid",
      "event_type": "ndaa_markup",
      "title": "HASC FY2027 NDAA Markup",
      "event_date": "2026-06-12",
      "event_time_utc": "13:00",
      "desk": ["defense"],
      "entity_ids": [],
      "source_url": "https://armedservices.house.gov/..."
    }
  ]
}
```

---

### Auth

#### `GET /auth/me`

Returns the authenticated user's profile and subscription tier. Used by Next.js on
session hydration to get authoritative tier from FastAPI (D012).

**Auth:** required

**Response `200`:**
```json
{
  "user_id": "uuid",
  "email": "user@example.com",
  "tier": "pro",
  "subscribed_at": "2026-01-15T14:22:00Z",
  "current_period_end": "2026-07-15T14:22:00Z"
}
```

---

### Stripe Webhooks

#### `POST /stripe/webhook`

Receives Stripe events. No Bearer auth — Stripe signature verification instead.

**Headers:**
```
Content-Type: application/json
Stripe-Signature: t=...,v1=...
```

FastAPI verifies the signature with `STRIPE_WEBHOOK_SECRET` before processing.
Invalid signature → `400` (logged to Sentry; not `401` to avoid leaking timing info).

**Handled event types:**

| Stripe event | Action |
|-------------|--------|
| `checkout.session.completed` | Create `subscriptions` row, set `tier = "pro"`, set `status = "active"` |
| `customer.subscription.updated` | Update `tier`, `status`, `current_period_start`, `current_period_end` |
| `customer.subscription.deleted` | Set `status = "cancelled"`, set `tier = "free"` |
| `invoice.payment_failed` | Set `status = "past_due"` |
| `invoice.payment_succeeded` | Ensure `status = "active"` (handles recovery from past_due) |

Unhandled event types → `200` (acknowledged but ignored; logged at DEBUG level).

**Response `200`:**
```json
{"received": true}
```

**Response `400` (bad signature):**
```json
{"error": {"code": "invalid_signature", "message": "Stripe signature verification failed"}}
```

---

### User Settings

#### `GET /users/follows`

Returns entities the user follows.

**Auth:** required  
**Tier gating:** pro only

**Response `200`:**
```json
{
  "follows": [
    {
      "entity_id": "uuid",
      "canonical_name": "Lockheed Martin Corporation",
      "entity_type": "company",
      "ticker": "LMT",
      "followed_at": "2026-05-01T10:00:00Z"
    }
  ]
}
```

---

#### `POST /users/follows`

Add an entity follow. Idempotent — re-following an entity already followed returns `200`.

**Auth:** required  
**Tier gating:** pro only

**Request body:**
```json
{"entity_id": "uuid"}
```

**Response `200`:**
```json
{"followed": true, "entity_id": "uuid"}
```

**Response `404` (entity not found):**
```json
{"error": {"code": "not_found", "message": "Entity not found"}}
```

---

#### `DELETE /users/follows/{entity_id}`

Remove an entity follow.

**Auth:** required  
**Tier gating:** pro only

**Path params:** `entity_id: UUID`

**Response `200`:**
```json
{"unfollowed": true, "entity_id": "uuid"}
```

---

### Admin

All `/admin/*` routes require `is_admin: true` in the JWT custom claims (D015).

---

#### `GET /admin/status`

Returns operational health snapshot.

**Auth:** required (admin)

**Response `200`:**
```json
{
  "timestamp": "2026-06-05T09:35:00Z",
  "briefs": {
    "defense": {
      "latest_status": "published",
      "latest_published_at": "2026-06-05T09:35:00Z",
      "faithfulness_score": 0.97
    }
  },
  "sources": {
    "usaspending": {
      "circuit_breaker": "closed",
      "last_successful_fetch": "2026-06-05T04:10:00Z",
      "last_run_status": "success",
      "last_run_records_new": 42
    },
    "sam_gov": {
      "circuit_breaker": "closed",
      "last_successful_fetch": "2026-06-05T03:45:00Z",
      "last_run_status": "success",
      "last_run_records_new": 18
    }
  },
  "llm_spend": {
    "today_usd": 0.09,
    "month_to_date_usd": 1.89,
    "daily_cap_usd": 5.00,
    "monthly_cap_usd": 50.00
  },
  "job_queue": {
    "pending_jobs": 2,
    "running_jobs": 1,
    "failed_jobs_last_24h": 0
  },
  "resolution_queue": {
    "pending_count": 14
  }
}
```

---

#### `GET /admin/resolution-queue`

Returns entity mentions awaiting human review.

**Auth:** required (admin)

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `status` | `"pending" \| "resolved" \| "new_entity"` | `"pending"` | Filter by status |
| `limit` | `int` | `50` | Max results (max 100) |
| `cursor` | `string` | — | Pagination cursor |

**Response `200`:**
```json
{
  "items": [
    {
      "id": "uuid",
      "raw_mention": "DRS Technologies",
      "normalized_mention": "DRS TECHNOLOGIES",
      "context_snippet": "...contract awarded to DRS Technologies for LRASM guidance...",
      "source_id": "dod_contracts",
      "confidence": 0.31,
      "candidates": [
        {
          "entity_id": "uuid-drs",
          "canonical_name": "DRS Technologies, Inc.",
          "ticker": "DRS",
          "score": 0.82,
          "match_method": "trgm"
        },
        {
          "entity_id": "uuid-leo",
          "canonical_name": "Leonardo DRS, Inc.",
          "ticker": null,
          "score": 0.61,
          "match_method": "semantic"
        }
      ],
      "created_at": "2026-06-05T04:22:00Z"
    }
  ],
  "next_cursor": "string | null",
  "total_pending": 14
}
```

---

#### `POST /admin/resolution-queue/{id}/resolve`

Resolve a queued mention to a canonical entity or flag for new entity creation.

**Auth:** required (admin)

**Path params:** `id: UUID`

**Request body — link to existing entity:**
```json
{
  "action": "link",
  "entity_id": "uuid"
}
```

**Request body — create new entity:**
```json
{
  "action": "create",
  "new_entity": {
    "canonical_name": "DRS Technologies, Inc.",
    "entity_type": "company",
    "desk": ["defense"],
    "identifiers": {
      "ticker": "DRS",
      "cik": "1234567"
    }
  }
}
```

**Request body — dismiss (not a trackable entity):**
```json
{"action": "dismiss"}
```

**Response `200`:**
```json
{
  "resolved": true,
  "action": "link",
  "entity_id": "uuid",
  "canonical_name": "Leonardo DRS, Inc."
}
```

---

## Pydantic model reference

Key models (implementation guide — full validation in FastAPI Pydantic schemas):

```python
class BriefSummary(BaseModel):
    id: UUID
    desk: str
    date: date
    status: Literal["published", "pending", "failed"]
    published_at: datetime | None
    headline: str | None
    bluf: str | None
    faithfulness_score: float | None

class BriefFull(BriefSummary):
    items: list[BriefItem] | None
    citations: list[Citation] | None
    sources_missing: list[str]
    model_waterfall: ModelWaterfallMeta | None
    staleness_indicator: StalenessIndicator | None
    tier_gate: str | None  # set when access is restricted (e.g. archived brief on free tier)

class BriefItem(BaseModel):
    id: UUID
    item_type: Literal["award", "filing", "policy", "macro", "signal"]
    headline: str
    body: str
    entity_ids: list[UUID]
    citation_ids: list[UUID]
    materiality_score: float | None
    display_order: int

class Citation(BaseModel):
    id: UUID
    source_id: str
    url: str
    fetched_at: datetime
    native_id: str
    license_class: Literal["public_domain", "licensed", "scrape_gray"]
    title: str | None
    excerpt: str | None

class StalenessIndicator(BaseModel):
    last_updated: datetime
    current_status: str
    message: str
```

---

## Environment variables

All secrets in environment variables; never hardcoded.

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key (never exposed to client) |
| `SUPABASE_JWT_SECRET` | JWT secret for local token verification |
| `STRIPE_SECRET_KEY` | Stripe API key |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |
| `OPENROUTER_API_KEY` | OpenRouter API key (all non-Anthropic models) |
| `ANTHROPIC_API_KEY` | Direct Anthropic SDK key (last-resort fallback) |
| `SENTRY_DSN` | Sentry error reporting |
| `LLM_MODEL_EXTRACTION` | `openrouter/deepseek/deepseek-v4-flash` |
| `LLM_MODEL_DISAMBIGUATION` | `openrouter/deepseek/deepseek-v4-flash` |
| `LLM_MODEL_SYNTHESIS` | `openrouter/deepseek/deepseek-v4-pro` |
| `LLM_MODEL_EVAL` | `openrouter/qwen/qwen3.7-max` |
| `LLM_MODEL_SYNTHESIS_FALLBACK` | `openrouter/qwen/qwen3.7-max` |
| `LLM_DAILY_BUDGET_USD` | Daily LLM spend cap (default `5.00`) |
| `BRIEF_GENERATION_CRON` | `30 10 * * *` (5:30am ET = 10:30 UTC) |
| `DATA_READINESS_CUTOFF_UTC` | `10:00` (5:00am ET = 10:00 UTC) |

---

## Service boundary notes

- `hpi-api` handles all HTTP: briefs, entities, calendar, auth relay, Stripe webhooks, admin.
- `hpi-worker` handles background processing: scheduler, ingestion adapters, brief generation. It does not expose HTTP endpoints (internal Fly.io network only for health).
- Next.js calls `hpi-api` for all data. It calls Supabase Auth JS client only for session management (token refresh, sign-in, sign-out).
- Both services read/write Supabase Postgres. `hpi-api` uses `SUPABASE_SERVICE_ROLE_KEY` for all DB operations (RLS bypass in trusted backend). Row-level security remains on as defense-in-depth.
