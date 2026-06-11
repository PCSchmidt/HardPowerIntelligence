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
  bypassed via direct Supabase PostgREST (SECURITY_AUDIT.md A01).

### Security
- No secrets in source or git history; constant-time webhook signature comparison;
  parameterized SQL throughout; RLS own-row isolation on all user tables.

### Known gaps before v1.0.0 deploy
- Dockerfiles (`docker/Dockerfile.api`, `Dockerfile.worker`) and Fly.io `fly.toml` configs
  not yet authored (DEPLOYMENT_CONFIG.md §6).
- Lemon Squeezy live credentials + webhook secret not yet provisioned (payments degrade
  gracefully until then — D045).
- Cloud migration apply (`supabase db push`) pending.

---

_No tagged releases yet. The first tag (v1.0.0) is emitted when Gate 9 (`deploy_ready`)
closes with the `GO` approval._
