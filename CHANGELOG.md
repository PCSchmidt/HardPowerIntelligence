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
- **Quiet-day reader UX** (2026-06-20): on a day a desk cleanly skips (no significant news, D085) or
  before the morning cron runs, the reader served the last published brief with *yesterday's date and no
  context* — which reads as stale/broken. The API now attaches a neutral `latest_available` indicator when
  the served brief isn't today's (distinct from the D013 pending/failed staleness), and the reader renders
  it as a calm informational note ("You're viewing the most recent brief…") rather than an amber warning.
  Turns "we don't pad on a quiet day" into a trust signal instead of a confusing stale date.
- **USAspending fetched-zero fix** (2026-06-20, Phase 1, refines D057): federal awards weren't reaching
  any brief — the source silently fetched 0 every run because its forward-advancing date watermark shrank
  the query window to ~1 day, and USAspending awards lag (they appear in the API weeks after their action
  date). Switched to a fixed 45-day rolling lookback with content-hash dedup. This restores defense-desk
  awards and unblocks entity minting (private contractors via UEI). Added `scripts/brief_quality_report.py`
  (read-only) to measure per-desk item/source/entity mix over a window.
- **Curation tuning, Step 1** (2026-06-19, refines D085): the strategic-significance gate now demotes
  *speculative financial vehicles* — SPAC/de-SPAC/blank-check combinations, cash-shell recapitalizations
  and rebrands, and vehicle-only term sheets — that were padding the AI desk, while still keeping
  substantive non-binding deals (e.g., a HALEU supply LOI). Prompt-only change, plus a durable curation
  eval (`scripts/eval_significance.py` + `tests/fixtures/significance_golden.json`); first run 12/12
  (froth 7/7 dropped, signal 5/5 kept).
- **Curation tuning, Step 2** (2026-06-19, desk identity): tightened the EDGAR convergence probes so the
  AI desk stops getting diluted by generic energy project finance. Demoted `grid-scale storage`,
  `transmission interconnection`, `power purchase agreement`, `solid-state battery`, and `geothermal`
  from `(energy, ai)` → `(energy)` — their AI link was only demand-side. Kept genuine AI∩Energy probes
  (hyperscale data center, liquid cooling, GPU, small modular reactor). Probe order unchanged.
- **License** (2026-06-19): the project is now explicitly **source-available under the PolyForm
  Noncommercial License 1.0.0** (`LICENSE`) — read/study/fork for noncommercial use; commercial use
  reserved to the author. Replaces the prior implicit all-rights-reserved (no-license) default.
- **Reliability + quality hardening** (post-Gate-8, D076–D086): LLM call-layer backoff for
  transient 429/5xx (D076); honest daily-run reporting + ingest resilience so a flaky source
  doesn't take the pipeline dark (D076/D079); EDGAR widened 8→40 probes (D077) + filing-body
  fact-extraction (D078) + SEC Form D private-placement ingestion (D081); GDELT media-attention
  Signal as labeled aggregate color (D082); a strategic-significance gate that drops
  true-but-trivial items (D085); analysis grounding made best-effort so a grounding hiccup never
  loses a passed brief (D086); the `/account` page (tier + Pro badge + manage-subscription, D080);
  UX Tier 1 — the at-a-glance ledger + provenance discoverability (D084, FRONTEND_SPEC §9); UX
  Tier 2a — per-type icons, inline magnitude bars, and trend-styled GDELT Signal (D087, frontend-only);
  a mobile-nav hamburger so all three desks are reachable on phones; signup landing on the brief
  (`/desk/defense`) instead of the upgrade page; honest free-tier onboarding copy with Pro surfaces
  degrading to "coming soon" while Lemon Squeezy is dark (D088); UX Tier 2b — a real GDELT Signal
  sparkline from a persisted lead-theme volume series (D089, migration `20260618000001`); a CI
  migration-reconcile safeguard so a schema change merged to `main` can't dark the daily brief (D090);
  and the first two gates of the **entity-resolution graph** (the moat, D091) — a SEC-seeded reference
  entity set (`scripts/seed_entities.py`, ~8k companies de-duped by CIK) and a precision-first resolver
  with an accuracy eval gate (`scripts/eval_resolver.py`; first run: precision 1.000 / false-link 0.000).
  Resolver recall fix: `normalize_mention` now strips the SEC state-of-incorporation tag (`/DE/`)
  that was dropping clean mentions like "Northrop Grumman" into the unresolved medium band, plus
  `scripts/renormalize_aliases.py` to backfill aliases already seeded under the old normalization
  (eval gate then passed on real data: precision 1.000 / recall 1.000 / false-link 0.000). T3.3
  (D092) wires resolution into brief generation: `brief_items.entity_ids` is now populated by
  resolving each item's source records (`engine/entity/linker.py`), and private/venture/gov
  entities are minted from authoritative identifiers (USAspending UEI, EDGAR CIK) — best-effort,
  so it never darks a brief; co-occurrence edges deferred (convergence derives from shared
  `entity_ids`, not edges). T3.4 surfaces the graph through the API: brief payloads carry a
  batched `entities` array (chip summaries — name/ticker/`is_private`) so the reader maps
  `item.entity_ids` → chips without an N+1, and `GET /entities/{id}` returns the Entity 360 core
  (identifiers, the desks an entity spans + a `convergence` flag, recent appearances). T3.5 renders
  **entity chips** on each brief item — public companies as name + ticker, closely-held/venture firms
  as a name-only "private" chip — backed by the resolution graph (the moat), not LLM-asserted.
  Verified end-to-end on a live defense brief (5/5 items linked correctly, zero false positives).
  T3.6 adds the **Entity 360 page** (`/entity/[id]`, noindex): the chips link into an identity card
  with identifiers, the desks the entity spans (a convergence line when ≥2), and recent appearances
  linking back to their briefs. T3.7 completes the sequence with the **cross-desk convergence tag** —
  the brief chip summary now carries a `convergence` flag (an entity that has appeared on ≥2 desks,
  the Defense∩AI∩Energy signal the product is built around), rendered as a highlighted chip; a GIN
  index on `brief_items.entity_ids` (migration `20260619000001`) backs the containment queries.
  **The entity-resolution graph (the moat) is now live end-to-end: reference set → eval-gated
  resolver → in-brief linking + private/venture minting → API → chips → Entity 360 → convergence.**
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

- **Layered analyst brief + reliability + freshness (2026-06-16)** — the brief evolved from a
  cited ledger into a layered analyst product, and the publishing path was hardened for unattended
  operation:
  - **Layered analysis (D071/D073)**: each item now carries a `read` (why it's material — analysis)
    and `watch` (forward catalyst), and the brief carries a `convergence_read` (cross-desk thesis),
    alongside the cited `body`. The analysis layer is held to *grounding*, not per-sentence citation
    (analyst voice: real domain context + hedged inference allowed; fabricated specifics flagged).
    A **regenerate-then-omit grounding gate** (`engine/brief/analysis.py`) rewrites a flagged field
    once, else stores `""` — so only grounded analysis is ever persisted/rendered. Migration
    `20260616000001` adds `read`/`watch` on `brief_items`, `convergence_read` on `briefs`.
  - **Drill-down UI (P3)**: BriefReader renders a "Convergence — HPI interpretation" block and a
    per-item collapsible "Analysis — HPI interpretation" disclosure (read + "What to watch" + a
    not-advice caption). Omitted fields render nothing. Live on `/desk/defense`.
  - **Provable-claim publish gate (D070)**: a brief publishes on `≥ brief_min_claims` (3) *provable
    claims* rather than item count — stable to how the synthesis packs facts into few/many items.
  - **Regenerate-on-failure + exception hardening (D072)**: `generate_publishable_brief` regenerates
    (up to `brief_max_attempts`, 3) on a failed gate *or* a generation exception (e.g. deepseek
    returning a whitespace-only non-JSON body), returning the best attempt — so a bad draw can't
    crash or dark-publish an unattended desk.
  - **Novelty / anti-rehash gate (D074)**: records already featured in a recent published brief
    (`novelty_window_days`, 7) are down-ranked (`novelty_penalty`, 0.5) so fresh items lead;
    demote-not-drop keeps the brief honest without forcing it empty.

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
- **Scheduled cadence** — `daily-brief.yml` cron is **enabled** (`0 9 * * *`, 09:00 UTC; ingest
  once → publish all 3 desks). Runs unattended; D072 makes a single bad draw/exception non-fatal.
- **Config (resolved 2026-06-16):** Supabase **Site URL + Redirect allowlist fixed** (signup/login
  emails now route to the prod domain — verified with a test signup). `SUPABASE_SERVICE_ROLE_KEY`
  set on Fly + `.env`, but note it is **not used by any service** (DB access is via `DATABASE_URL`;
  auth via `SUPABASE_JWT_SECRET`) — reserved for future Supabase Admin API use.
- Minor: verify the OpenRouter model IDs (non-fatal litellm "Provider List" log noise). deepseek
  occasionally returns a whitespace-only body; the fallback + D072 retry now absorb it.

---

_Deployed to production 2026-06-12 but not yet tagged. The first tag (v1.0.0) is emitted
when Gate 9 (`deploy_ready`) is formally closed with the `GO` approval — pending Lemon
Squeezy + public-launch readiness._
