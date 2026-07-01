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

- **Full Wire: the material overflow the brief drops for space is now accessible** (2026-06-30,
  D112): the curated brief is space-capped, so on a heavy news day material, on-thesis items that
  cleared scoring fell off and were discarded. They're now persisted (`brief_wire` table) and
  surfaced on a per-desk `/desk/{desk}/wire` page — title + source + link, no narrative, ranked by
  materiality — linked from each desk reader ("See the full wire — everything that didn't fit").
  Scope is material-overflow only: froth the significance gate rejected and items already featured
  in the brief are excluded. New public endpoint `GET /wire/latest?desk=` (free tier, same access
  as the current desk). Written best-effort after the brief commits, so it can never dark a brief;
  degrades to empty if the migration isn't applied. +10 tests; backend 464 green, web 18 green.
  Goes live after the migration push + API/web redeploy.

### Fixed

- **Daily brief desks now run in parallel — the last desk stops getting cut off** (2026-07-01, D113): the 7/1
  run was cancelled at the 45-min timeout with Energy never published (same shape as 6/29). The three desks were
  generated sequentially in one job, so their times summed and a slow-LLM day starved the last one. Split the
  workflow into a single `ingest` job plus a per-desk `brief` matrix so defense/ai/energy generate concurrently,
  each with its own 30-min ceiling and `fail-fast: false`. Wall-clock is now ingest + the slowest single desk,
  not the sum. Takes effect on the next scheduled run.
- **SAM.gov ingests again — its 404 means "no match," not a broken endpoint** (2026-07-01, D114): SAM returned
  0 records because the runner treated SAM's `404` as a fatal error and failed the whole source on the first
  probe. Per GSA docs, that 404 is the API's "no opportunity matches your search" signal. Aligned the base URL
  to the documented `https://api.sam.gov/opportunities/v2/search` and added an `empty_response_statuses` adapter
  hook so the runner treats a declared status (SAM → 404) as an empty page and keeps walking the other probes.
  Follow-up noted: title-only search is narrow; NAICS/PSC code filters are the real fix if volume stays low.
- **Curation: Defense/AI no longer flooded by DOE grants; convergence boost is now a tiebreak** (2026-06-30,
  D111): the 6/30 desks read wrong — Defense led with small DOE/NASA awards over its actual thesis, and the
  AI desk ranked "smaller DOE awards" above on-thesis research. Two root causes, three fixes: (1) re-homed the
  USAspending `("rare earth","critical minerals")` convergence probe from defense-first to **energy-first** so
  those grants land on Energy (where they read well) and Defense keeps its thesis; (2) rebalanced materiality
  weights (authority 0.25→0.30, novelty 0.30→0.20, magnitude 0.20→0.25) — flat novelty couldn't rank same-day
  items, so it was trimmed into authority+magnitude; lifting authority keeps no-dollar news/research signals
  competitive rather than buried — plus sharper sub-$10M buckets so tiny grants sink; (3) changed the
  cross-sector convergence boost from **multiplicative to additive** (default 0.15→0.02) so a small multi-desk
  grant can't overpower a 20×-larger single-desk award — it's a tiebreak, not a dominator. Takes effect on the
  next desk run. Backend suite 454 green.

- **GDELT User-Agent + SAM.gov endpoint fixes** (2026-06-30, D110): the 6/30 run published all three desks
  (timeout fix held) but GDELT, SAM.gov, and EDGAR failed at ingest. GDELT was 429ing on the *first* request
  — it blocks anonymous/default library user-agents, so the adapter (and the signal client) now send a
  browser-style UA, matching how the SITREP app pulls GDELT cleanly. SAM.gov 404'd because the endpoint was
  missing the `/prod/` path segment and used a nonexistent `q` keyword param — corrected to
  `/prod/opportunities/v2/search` with the `title` search field. EDGAR's 500 was confirmed SEC-side (the
  endpoint and SEC-compliant UA are correct) — no code change, monitor only. Backend suite 454 green.
- **GDELT stories now flow instead of 429-storming** (2026-06-29, D109): the news-radar adapter fired ~50
  single-phrase probes back-to-back and GDELT (rate-limited ~1 req/5s) returned HTTP 429 on all of them —
  the source yielded zero. Following the SITREP app's approach, the ~50 probes are now OR-combined into ~8
  bounded per-desk queries and the runner spaces GDELT requests by ≥5s, so the walk stays under the limit.
  Also fixed two RSS feeds that had moved (The Register, Tom's Hardware) and were being skipped. +6 tests;
  backend suite 453 green.
- **Daily run no longer times out — GDELT signal fails fast** (2026-06-29, D108): the 6/29 scheduled run
  was killed at the 30-min timeout with only Defense published (AI cut off mid-synthesis, Energy never
  ran). GDELT rate-limits hard (HTTP 429), and the decorative media-attention Signal was fetching 6 themes
  per desk through the full 4-attempt/20s-backoff budget — ~3 min of dead waiting per desk. The Signal now
  uses a fail-fast fetcher (one attempt; degrades to no Signal block on 429). Also moved the cron 09:00 →
  06:00 UTC (GitHub delays scheduled runs 40–100 min) and raised the job timeout 30 → 45 min. Backend
  suite 447 green. (GDELT *story* ingestion still 429s — restoring it via SITREP-style OR-combined queries
  with request throttling is a separate follow-up; it's non-fatal since briefs publish from the RSS feeds.)
- **Cross-desk filing duplication — one filing now homes on one desk** (2026-06-28, D107): the same SEC
  filing was printing on two desks (Energy Fuels' rare-earth deal and REalloys' $100M placement showed on
  both Energy and AI; the AI desk even led with "Defense Tech and Energy Deals Dominate"). Cause was in
  ingest, not D097 routing: EDGAR parses one filing once per matching `(query, desk)` probe, and each copy
  carried a probe-specific `content_hash`, so the `raw_records` dedup never collapsed them → many records
  per filing, each with a different home desk. Fixed with an opt-in `merge_by_native_id` pass in the
  ingestion runner that keeps one record per `(source_id, native_id)`: desks are unioned (the convergence
  signal survives) and the home desk is taken from the most-specific probe (fewest desks wins; ties broken
  by a fixed order). Takes effect on the next ingest run. +8 unit tests; backend suite 447 green.

### Changed
- **Brief is a comprehensive desk read — item ceiling 8 → 25** (2026-06-28, D100, supersedes D039): a desk
  brief now aims to cover its domain thoroughly, not skim it. Raised `BRIEF_MAX_ITEMS` to 25 and reworked
  the synthesis prompt — which had hard-instructed "target 2–3 items" (a thinness cause as real as the cap)
  — to write one substantive item per genuine development up to the cap, with explicit no-padding / no-
  fabrication guardrails. Enriched the BLUF into a 4–6 sentence state-of-the-domain narrative and added
  desk-discipline language reinforcing D097 routing. The significance froth filter is unchanged: more
  content comes from more *sources*, not a looser filter. Note: output is supply-limited — it fills toward
  25 only as source breadth (P3) grows; with 4 adapters built, desks still produce ~3–6 items today.
- **Publish-path flip — grounding labels, no longer suppresses** (2026-06-28, D099): the publish gate
  no longer fails a brief for falling under a provable-claim floor (the retired D070 gate). A brief now
  publishes when it has at least one honest, non-fabricated item, and every item is stamped a confidence
  label (confirmed / reported / analysis / speculative; new `brief_items.attribution` column, surfaced via
  the briefs API). Thin desks publish labeled instead of going dark. The one hard line is unchanged: an
  item with no source-supported content is still excluded (anti-fabrication, D069), and the analysis
  grounding gate (D071/D073) is untouched. The reader confidence chip is the next gate. Publish tests
  rewritten to the new contract; suite 411 green.

### Changed
- **Probe top-up — remaining cutting-edge clusters** (2026-06-28, D103): closed the gaps D102 left.
  Defense contested logistics (contested logistics, military biomanufacturing, autonomous resupply,
  cyber-EM warfare); AI networking fabric + efficiency (NVLink, Ultra Ethernet, optical circuit
  switching, DPU/SmartNIC, Groq/LPU, mixture-of-experts); energy next-gen hydro + grid-component crunch
  (hydrokinetic, closed-loop geothermal, transformer/copper shortage). GDELT ~52 probes, EDGAR ~65.
- **Probe vocabulary expanded to the cutting-edge fronts** (2026-06-28, D102): from an operator topic
  review, the search vocabularies now systematically name the current cutting-edge topics, not just the
  basics. GDELT news probes grew from ~5/desk to ~12/desk plus a Space∩Energy∩AI convergence cluster
  (39 total): defense autonomy / directed energy / space / quantum-PNT (CCA, drone swarm, UUV, HEL, HPM,
  hypersonics, missile defense, quantum sensing, pLEO, SSA); the AI compute stack (Blackwell, TPU, HBM,
  advanced packaging, silicon photonics, EUV, immersion cooling, inference chips); energy (microreactor,
  TRISO, enhanced geothermal, perovskite, NiZn, iron-air, LDES, TES, VPP); and SBSP / orbital data
  centers. EDGAR filing probes gained 18 of the same terms (home-desk-tagged, pinned positions intact);
  NRC added microreactor + TRISO. Demarcation (D097) preserved; volume stays bounded by materiality, the
  significance gate, and the 25-item cap. A coverage test guards the topics from silent regression.

### Added
- **Generic RSS/Atom feed adapter — the breadth scale lever** (2026-06-28, D104): one configurable
  adapter ingests a registry of ~21 named outlets (trade press, think tanks, company IR — Breaking
  Defense, Data Center Dynamics, IEEE Spectrum, Utility Dive, World Nuclear News, CSIS, RAND, CSET, …),
  each tagged to a home desk. Onboarding an outlet is one registry line, not a build — Phase 1 of the
  source-breadth plan (see docs/SOURCE_LANDSCAPE.md). A named outlet is attributed reporting → the
  **Reported** confidence tier (vs GDELT's raw firehose → Speculative); `scrape_gray` (outlet + title +
  short snippet + link only, HTML stripped). RSS 2.0 and Atom both parsed (stdlib); per-feed fetch
  isolation in `enrich` so one dead feed can't abort the rest. 9 tests; suite 433 green. Per-feed
  license/reliability overrides and entity linking are documented follow-ups.
- **GDELT-as-story source — worldwide news radar** (2026-06-28, D101): GDELT's global news index now
  feeds brief *items*, not just the aggregate Signal line. A curated, on-thesis query per desk-theme
  (≈5/desk, English-only, capped) via the keyless DOC 2.0 ArtList API; each article becomes a `news`
  record tagged to its single home desk. Lands as **Speculative**, link-only (`scrape_gray`: title +
  link, never article body), reusing `source_id="gdelt"` so it carries low materiality weight and the
  speculative confidence label automatically — the radar that fills out the comprehensive desk read
  (D100) below the primary-record spine. Unblocked by the epistemic flip (D098/D099). First adapter of
  the P3 source-breadth push. Citation `license_class` now derives from the source (gdelt → scrape_gray)
  instead of a hardcoded value. 12 tests; suite 423 green. Source activated via migration; entity
  linking and a Reported-tier promotion for vetted outlets are planned follow-ups.
- **Epistemic-framing taxonomy** (2026-06-27, D098, widen-the-net keystone): the deterministic vocabulary
  for grading every item by its basis — a single ordered ladder, Confirmed (primary record, cited) →
  Reported (attributed, not primary) → HPI analysis (synthesis/inference) → Speculative (early/weak signal).
  `classify_item` derives the tier from signals already in the pipeline (source evidence class + whether the
  claim was citation-supported), with no LLM call and no new fabrication surface. This is the foundation for
  retiring "every claim cites the public record" as an *admission gate*: a primary-record claim that isn't
  individually cited becomes *labeled* HPI analysis instead of being dropped; an unclassified source defaults
  to Reported, never silently Confirmed. Pure module + 11 tests; the publish-path flip (keep-and-label),
  persistence, and reader chip follow next gate. Suite 409 green.
- **Primary-desk routing — desk-bleed fix** (2026-06-27, D097): each item now appears on ONE home desk
  (the first, primary entry of its desk array) instead of duplicating onto every desk it touches. A
  cross-desk record — an AI∩Energy data-center filing, a Defense∩AI autonomy paper — used to print on
  both briefs, so each desk read like an everything-desk. Cross-desk relevance survives as the convergence
  signal it should be (the materiality boost + entity chip), not a duplicate item. Scoring still sees the
  full cross-desk neighborhood (corroboration and amount-normalization unchanged); only the surfaced set is
  narrowed, via a pure `_is_home_desk` predicate. +4 unit tests; suite 398 green. P0 phase 1 (desk
  demarcation); widen-the-net epistemic-framing layer is next.
- **NRC entity-linking** (2026-06-20, D096, completes D095's deferral): NRC documents now feed the
  entity-resolution graph — an NRC notice about Oklo or Centrus produces an entity chip and cross-desk
  convergence, the same as an EDGAR filing or a USAspending award. Since NRC docs carry no ticker/CIK/UEI
  (and short-name trigram matching is fragile), the adapter attaches a *known ticker* for thesis-relevant
  public nuclear/fuel-cycle companies named in a document and resolves via the resolver's exact-identifier
  path (false-link-proof). A curated allowlist (Oklo, NuScale, Centrus, BWXT, Constellation, Vistra, …);
  a name not on it produces no mention, so precision holds. No linker/resolver change was needed — the
  existing machinery already resolves a ticker-bearing mention. +2 adapter tests; suite 394 green.
- **NRC source breadth for the Energy desk** (2026-06-20, D095): the Energy desk was consistently the
  thinnest (Phase B) because every desk ran on the same capital-flow sources — no *regulatory* signal.
  Added a fourth adapter, **NRC via the Federal Register API** (free, no key, public-domain): five on-thesis
  probes (small modular reactor, advanced reactor, HALEU, combined license, uranium enrichment) pull
  nuclear/SMR licensing events that lead the money by months. Regulatory documents have no dollar amount, so
  they score on source authority (`source_weights['nrc']=0.85`) + novelty like arXiv, and the synthesis model
  classifies them as `policy` items. The source self-activates in the daily pipeline (the cron's `supabase db
  push` seeds the registry row, `run_ingest.py` reads all registered sources). v1 emits no entity mentions —
  NRC docs carry no ticker/CIK/UEI, so name-only resolution is a deliberate follow-on. Chose NRC over the EIA
  macro API (which needs an operator-provisioned key and is monthly/slow). 24 adapter tests; suite 392 green.
  See DECISIONS.md D095.
- **Frontend test infrastructure** (2026-06-20, D094): the web app had no test runner — only `next build`
  typechecked it, nothing exercised its growing client-side logic. Added **Vitest 4 + Testing Library
  (jsdom)** with a first suite (16 tests) over the amount-parsing helpers (`lib/amounts.ts`), SEC-title
  casing (`lib/entities.ts`), and the D093 onboarding component's localStorage/dismiss behavior. Run with
  `npm test`. Deliberately skips `@vitejs/plugin-react` (its Babel chain conflicts with the modified Next's
  pinned `@babel/core`) — Vitest's built-in oxc transform handles React 19 JSX with no plugin. Test files
  stay in the root `tsconfig` so `next build` typechecks them too. See DECISIONS.md D094.
- **First-run reader orientation** (2026-06-20, D093, tester-readiness): the brief reader is dense — a
  cited at-a-glance ledger, an expandable analysis layer, citation superscripts, and convergence chips —
  and a first-time tester got no orientation. Added a one-time, dismissible "New here?" legend at the top
  of the reader that points at the three affordances a reader most needs (every claim is cited; analysis is
  kept separate from facts; convergence chips flag cross-desk companies), using the *real* UI marks as the
  legend so it teaches by recognition. Dismissal persists per-browser in `localStorage`; client-only and
  mount-gated so a returning reader never sees a flash. Frontend-only (`web/components/brief/reader-onboarding.tsx`).
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
