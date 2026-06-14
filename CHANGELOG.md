# Changelog — Hard Power Intelligence

All notable changes to this project. Format based on
[Keep a Changelog](https://keepachangelog.com/); this project versions releases at the
deploy gate (Gate 9 `tag-release.sh`). Cycle 1 launched Defense-first; post-launch the engine
went multi-desk (Defense / AI / Energy) around the convergence north-star (D060).

## [Unreleased] — toward v1.0.0

First production release: a multi-desk (Defense / AI / Energy) web reader with verified,
cited briefs, organized around the Defense∩AI∩Energy **convergence** thesis (D060), fed by a
live ingestion runner, with Supabase auth and Lemon Squeezy subscriptions. Built gate-by-gate
(Gates 1–8 closed).

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
- **Multi-desk brief generation (2026-06-14)**: `generate_brief(desk)` is genuinely
  desk-scoped (D062) — candidate scoring + RAG retrieval filter to `desk = ANY(nr.desk)`
  (membership, so multi-desk convergence records surface in every relevant desk) and the
  synthesis prompt uses a desk-aware analyst persona. `daily-brief.yml` offers all three desks.
- **Convergence north-star (2026-06-14)**: the product is organized around the Defense Tech ∩
  AI ∩ Energy convergence (D060); three desks feed a flagship cross-domain convergence brief.
  Materiality now applies a **cross-sector boost** — a record touching ≥2 desks scores higher
  (`MATERIALITY_CROSS_SECTOR_WEIGHT`, default 0.15).
- **SEC EDGAR adapter (2026-06-14)**: first cross-desk source (`engine/adapters/edgar.py`,
  D061) — EDGAR full-text search over 8-K filings, driven by convergence-themed probes each
  tagged to the desk(s) it serves (one adapter feeds Defense + AI + Energy; multi-desk tags
  are the convergence signal, D060). Runner now passes adapter `headers` (SEC User-Agent).
  Deferred: company-facts/XBRL capex, Form 4/13F ownership, full-text body. 16 tests; live
  smoke test surfaced NuScale (SMR), Palladyne AI (autonomy), Skyworks (rare earth/semis).
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
- **Defense desk scoped by technology, not agency (D059)**: the USAspending adapter filters by
  a PSC-informed defense-tech keyword set (space, directed energy, drones, ISR, autonomy,
  hypersonics, EW) across all agencies — so the desk is "Defense Tech" (NASA/DoD/DHS/DOE),
  not generic federal contracts. The deterministic pre-filter pattern reused by every desk.
- **Materiality scoring — cross-sector convergence boost (D060)**: a record touching ≥2
  desks (e.g. an EDGAR "rare earth" filing tagged defense+ai+energy) has its score multiplied
  by `(1 + weight·(desks−1))`, capped at +2 desks (`MATERIALITY_CROSS_SECTOR_WEIGHT`, default
  0.15). Single-desk records are unaffected. Makes every brief convergence-aware — the
  cross-domain signal ranks highest, the mechanical expression of the north-star.
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
- **Brief reproducibility + citation enforcement (D058)**: synthesis + eval now run at
  `temperature=0` (the first live run swung 0.000↔0.750 on identical data); uncited sentences
  are dropped before scoring (publish only what's provable); `persist_brief` is idempotent on
  `(desk, date)` (delete-before-insert), so re-runs replace and a passing brief supersedes a
  failed one. First live-data Defense brief published at faithfulness 1.000.
- **DB connection retry (D057)**: `create_pool` retries transient connection failures (DNS
  `getaddrinfo`, refused/reset) with backoff — a momentary Supabase-pooler DNS blip no longer
  aborts an unattended ingest/brief run. `run_brief`/`seed_fixtures` route through it too.

### Security
- No secrets in source or git history; constant-time webhook signature comparison;
  parameterized SQL throughout; RLS own-row isolation on all user tables.

### Known gaps before public launch
- **Lemon Squeezy not set up** — checkout shows "not configured" (D045 graceful
  degradation). Checkout creds go in Vercel; webhook secret on Fly.
- **AI / Energy desk depth** — both desks are wired (D062) and fed cross-desk by EDGAR, but
  need dedicated sources for real depth (EIA/NRC + interconnection queues for Energy; more
  AI-infra sources). Until then their daily volume may fall below `BRIEF_MIN_ITEMS`.
- **Flagship convergence brief** — the cross-domain brief (D060) that synthesizes across the
  three desks is not yet built; the desk briefs + cross-sector boost are its substrate.
- **Scheduled cadence** — the runner is run manually; `daily-brief.yml` (ingest → brief) is
  the interim trigger, its cron still commented until source coverage justifies daily spend.
- **Config:** Supabase Site URL points at another project (email-confirmation links
  misroute); the `.env` `SUPABASE_SERVICE_ROLE_KEY` is wrong (unused by deployed services
  but should be corrected).
- Minor: verify the OpenRouter model IDs (non-fatal litellm "Provider List" log noise).

---

_Deployed to production 2026-06-12 but not yet tagged. The first tag (v1.0.0) is emitted
when Gate 9 (`deploy_ready`) is formally closed with the `GO` approval — pending Lemon
Squeezy + public-launch readiness._
