# Changelog — Hard Power Intelligence

All notable changes to this project. Format based on
[Keep a Changelog](https://keepachangelog.com/); this project versions releases at the
deploy gate (Gate 9 `tag-release.sh`). Cycle 1 = Defense desk, web-only.

## [Unreleased] — toward v1.0.0

First production release: the Defense desk web reader with verified, cited briefs,
Supabase auth, and Lemon Squeezy subscriptions. Built gate-by-gate (Gates 1–8 closed).

### Added
- **Data pipeline** (Gate 4): USAspending adapter + entity resolver
  (contractor → ticker/CIK/UEI), proven against golden fixtures.
- **Brief engine** (Gate 5): brief generator + citation-faithfulness eval harness;
  every claim links to a source at/above the faithfulness threshold (baseline 1.000).
- **Web reader** (Gate 6): Next.js App Router app — marketing home, Defense desk reader,
  brief/[id], subscribe flow; Supabase auth via `@supabase/ssr`; FastAPI as the single
  data boundary (D011).
- **FastAPI service** (`hpi-api`): briefs/calendar/auth endpoints, JWT verification
  (Supabase JWKS + HS256 fallback), Lemon Squeezy webhook with HMAC verification.
- **Database**: 16-table schema with RLS, pgvector, and Storage bucket (Supabase).
- **Security audit** (Gate 8): OWASP Top 10 + AI-threat review — PASS, 0 Critical/High
  (`SECURITY_AUDIT.md`).
- **Brand**: parchment-equations backdrop motif recorded for the web reader (D051).
- **Deployment config**: `DEPLOYMENT_CONFIG.md` — Vercel + Fly.io + Supabase topology
  and env/secrets matrix.
- **Production ingestion runner (2026-06-14)**: `engine/ingest/` + `scripts/run_ingest.py`
  — the live-data replacement for `seed_fixtures.py` (D004, D055, D057). Pulls fresh source
  data through a retry/backoff HTTP fetcher, dedups into `raw_records` via the DB unique
  constraint, normalizes + embeds only new records, advances per-source cursors, records
  `ingestion_runs` provenance with a circuit breaker, and prunes the hot window (retention
  preserves cited records). USAspending wired live; `daily-brief.yml` now ingests before
  briefing. 19 new tests (fetcher/runner/retention); live smoke test parsed 100 real awards.
- **Production deployment (2026-06-12)**: live end-to-end — web (Vercel,
  `hard-power-intelligence.vercel.app`), API (Fly.io, `hpi-api.fly.dev`), Supabase cloud.
  First cited brief published to `/desk/defense` at faithfulness 1.0. Includes Fly
  Dockerfiles + `fly.toml`, `.dockerignore`, `DEPLOY_RUNBOOK.md`, and the interim
  `daily-brief.yml` GitHub Actions workflow.

### Changed
- **Payments**: switched from Stripe to **Lemon Squeezy** (Merchant of Record) to absorb
  global VAT/GST liability for a solo-operated product (D050). Pricing unchanged
  ($19/mo, $179/yr, 14-day trial).
- **Gate 7 test runner**: frontend gate now runs `next build` instead of bare
  `tsc --noEmit` (Next.js 16 typed-routes require the plugin-aware program); backend uses
  `uv run pytest` (D052).

### Fixed
- **Reproducibility**: added `[tool.uv.sources]` so the workspace provisions from a clean
  checkout (`uv sync` previously failed to parse the api/worker → `hpi-engine` dependency
  graph); committed `uv.lock` (D052).
- **Security (briefs paywall)**: migration `20260611000001_lock_briefs_rls.sql` removes
  client read access to briefs/citations/entities so the Pro/archive paywall can't be
  bypassed via direct Supabase PostgREST (SECURITY_AUDIT.md A01). Applied + verified on
  cloud 2026-06-12.
- **RAG retrieval (HNSW)**: replaced the ivfflat embedding index with HNSW — ivfflat with
  `probes=1` returned 0 passages on sparse data, so no brief could publish (D053).
- **API auth (ES256)**: `pyjwt[crypto]` so the API verifies cloud Supabase's ES256 tokens;
  without `cryptography`, every authenticated request 401'd in production (D054).

### Security
- No secrets in source or git history; constant-time webhook signature comparison;
  parameterized SQL throughout; RLS own-row isolation on all user tables.

### Known gaps before public launch
- **Lemon Squeezy not set up** — checkout shows "not configured" (D045 graceful
  degradation). Checkout creds go in Vercel; webhook secret on Fly.
- **No production ingestion runner** — briefs run from seeded golden fixtures, not live
  government data. Fresh daily cadence needs the ingestion runner (unbuilt `hpi-worker`,
  D004); GH Actions `daily-brief.yml` is the interim bridge.
- **Config:** Supabase Site URL points at another project (email-confirmation links
  misroute); the `.env` `SUPABASE_SERVICE_ROLE_KEY` is wrong (unused by deployed services
  but should be corrected).
- **`persist_brief`** not idempotent for same-day reruns (UniqueViolation on (desk, date)).
- Minor: verify the OpenRouter model IDs (non-fatal litellm "Provider List" log noise).

---

_Deployed to production 2026-06-12 but not yet tagged. The first tag (v1.0.0) is emitted
when Gate 9 (`deploy_ready`) is formally closed with the `GO` approval — pending Lemon
Squeezy + public-launch readiness._
