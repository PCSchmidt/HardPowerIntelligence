# Data Architecture Analysis — Hard Power Intelligence

> A deep-think companion to [`general_data_source_notes.md`](../general_data_source_notes.md)
> (the raw Gemini/ChatGPT/Claude source-survey) and [`DATA_SOURCES.md`](DATA_SOURCES.md)
> (the tiered source map). Purpose: decide *how* we collect and process data across the
> Defense, AI, and Energy silos to build the best product **within a cost-constrained,
> solo-operated subscription model** — not just *which* sources exist. Status: analysis /
> recommendations / open questions. No decisions are locked here; the ones worth locking
> are flagged for `DECISIONS.md`.

---

## TL;DR — the core bet

The source survey collects ~40 candidate feeds. The catalog is not the hard part — it's
already over-supplied. The three findings that actually matter:

1. **We have a strategy conflict to resolve.** The raw notes treat **GDELT / global news
   as the spine**. The existing `DATA_SOURCES.md` treats **free structured government /
   regulatory data as the spine and news as commodity**. These are different products with
   different cost curves. **Recommendation: structured-primary, news-secondary.** The
   structured bet is cheaper, more defensible, and already half-built. News is a
   *corroboration and narrative* layer, not the source of record.

2. **The bottleneck is the ingestion harness, not the source list.** We have exactly one
   adapter (`usaspending`) and *no* production runner (D004 `hpi-worker` is unbuilt; briefs
   run from seeded fixtures). The highest-leverage work is the durable harness that makes
   adding the *next* source a half-day job — scheduler, dedup, cursors, retries,
   `source_runs` accounting. Architecture beats catalog.

3. **The moat is the entity graph and the cross-domain edges, not the feeds.** "AI data
   centers are driving nuclear/grid buildout" is one story told across all three silos. The
   value is connecting a contractor → ticker → SEC capex disclosure → interconnection-queue
   filing → power-purchase news — with provenance. Sources are commodities; the *graph over
   them* is the product.

Everything below expands these and ends with the open questions I need you to answer.

---

## 1. Where we actually are today (honest baseline)

| Layer | Built? | Notes |
|-------|--------|-------|
| Adapter pattern (`NormalizedRecord`, `parse()` / `build_request_payload()` / `next_cursor()`) | ✅ | Clean, source-agnostic. Good foundation. |
| Adapters implemented | 🟡 **1 of N** | `usaspending` only. Defense desk only. |
| Entity resolver | ✅ | `engine/entity/resolver.py` — name → ticker/CIK/UEI. |
| Raw → normalized → embed → brief pipeline | ✅ | `brief/generator.py`, pgvector RAG, materiality scoring, citation-faithfulness eval. |
| **Production ingestion runner** | ❌ | No scheduler. No `source_runs` loop. `hpi-worker` empty (D004). |
| Fresh data | ❌ | Briefs synthesize from **seeded golden fixtures**, not live feeds. |
| Sources beyond US federal contracts | ❌ | No SEC, no EIA, no news, nothing global. |

**Implication:** we are one adapter and zero runners into a 40-source plan. The plan is not
the constraint. The *machine that runs adapters on a schedule and keeps the lights on* is.

---

## 2. Finding 1 — Reconcile the two competing philosophies

The two strategy documents disagree about the center of gravity:

| | `general_data_source_notes.md` (the survey) | `DATA_SOURCES.md` (the existing map) |
|---|---|---|
| Spine | GDELT / global news firehose | Free structured gov/regulatory data |
| Primary signal | "Where is attention spiking globally" | "What was actually awarded/filed/built" |
| LLM load | **High** — must triage a noisy firehose | **Low** — structured data is pre-parsed |
| Provenance | Article URLs (copyrighted, link-only) | Primary-source records (citable, redistributable) |
| Licensing risk | Real (ACLED, GTA, IEA, news APIs) | Minimal (public-domain gov data) |
| Differentiation | Low ("a GDELT dashboard" — commodity) | High (synthesis over primary records) |

**My read:** the structured-first posture in `DATA_SOURCES.md` is the stronger bet and it's
the one we've half-built. A news-first product is *more expensive to run* (you pay LLMs to
separate signal from a torrent of reprints) and *less defensible* (anyone can point an LLM
at GDELT). Even ChatGPT's own answer in the notes lands here: *"your value is not access to
GDELT… it's curation, entity resolution, citations."*

**So the role of news/GDELT is demoted to three specific, cheap jobs:**

- **Early-warning / discovery** — surface that *something* is happening around a tracked
  entity before it shows up in a filing or award, so we know where to point the structured
  collectors.
- **Corroboration** — "this award is consistent with N news mentions this week" raises
  materiality/confidence scores without the news *being* the cited claim.
- **Narrative color** — a linked, short-quoted human-readable framing around the
  primary-source facts.

News never becomes the source of record for a claim in a brief. Primary structured records
are. This keeps citations clean, licensing safe, and LLM spend bounded.

> **Candidate decision (D0xx):** *Structured primary-source data is the spine; news/GDELT
> is a secondary discovery + corroboration layer and is never the sole citation for a
> brief claim.*

---

## 3. Finding 2 — The harness is the product, not the catalog

Adding a source should be: write an adapter (`parse` + request-builder, ~the size of
`usaspending.py`), register it, done. That's only true if the surrounding machine exists.
It doesn't yet. The harness needs:

- **A scheduler with per-source cadence.** Not everything is 15-minute. A *daily* brief does
  not need a 15-min GDELT poll — that's pure cost with no product benefit. Cadence should be
  matched to publish rhythm: structured daily, news hourly *at most*, slow refs weekly.
- **`source_runs` accounting** — last cursor, last success, rows ingested, errors,
  rate-limit state. This is what makes incremental pulls and backfill possible and what you
  look at when a source goes quiet.
- **Deterministic dedup before the LLM.** `content_hash` exists on `NormalizedRecord` — use
  it as the first gate. Then embedding-cluster near-duplicates (the same event reported by
  20 outlets) so we **synthesize once, not 20×**. Dedup is a direct cost lever.
- **Rate-limit / retry / backoff** as a shared concern, not per-adapter. (We already hit
  transient DNS flakiness in deploy; the runner must assume the network is hostile.)
- **License-class enforcement at ingest** (see §6) so "link-only" data can never leak into a
  republished body.

**Recommendation:** the real Cycle-2 deliverable is *this runner* (a thin scheduler + the
`source_runs` loop), reusing the existing adapter contract — **not** a pile of new adapters.
Two or three high-value adapters on top of a solid runner beats ten adapters duct-taped to a
cron. The interim `daily-brief.yml` GitHub Action is fine as the *trigger* for now; the
*logic* (cursoring, dedup, accounting) is what needs to exist.

---

## 4. Finding 3 — Cost center-of-gravity is LLM triage; shrink the funnel

Infra cost here is nearly fixed and tiny (Fly + Supabase + Vercel). **The variable cost is
LLM tokens, and it scales with how much low-signal text you push through the funnel.** A
news-heavy strategy is, mechanically, a token-heavy strategy.

The notes' two-tier pattern (cheap model triages, premium model synthesizes) is correct but
it's the *second* lever. The *first* lever is to keep junk out of the LLM entirely with
**deterministic pre-filters**, which cost ~nothing:

1. **Structured sources need almost no triage** — a USAspending award is already clean,
   typed, entity-bearing. Embed + synthesize. This is why structured-first is also
   cheapest-first.
2. **For news, filter before the model:** GDELT theme codes + an **entity allowlist** (only
   articles co-mentioning a tracked entity/ticker/agency) + tone/recency thresholds. This
   can cut the firehose 100× before a single token is spent.
3. **Dedup before triage** (see §3) — never pay to read the same event twice.
4. **Then** the cheap model classifies/extracts on the survivors, and **only** the top-N
   scored items per desk reach the premium synthesis model (D006 waterfall) — which we
   already have, with a citation-faithfulness gate.

Net: the cost story and the quality story point the same way as the structured-first bet.
The cheapest pipeline is also the highest-provenance one.

> A useful budget framing to validate: target a **fixed cents-per-desk-per-day** synthesis
> cost, and treat any source whose triage cost exceeds its signal contribution as a
> candidate for a *harder* deterministic pre-filter, not a bigger model.

---

## 5. Finding 4 — The moat is the entity graph and cross-domain edges

The single best product insight buried in the notes (Claude's energy-intersection query,
ChatGPT's "defense + AI + energy are increasingly one system") is **convergence**: the AI
buildout is a *power-demand* story is a *grid/nuclear* story is a *defense-industrial* story.
The thing no competitor trivially replicates is the **graph that connects them with
provenance**:

```
contractor (USAspending award)
   → resolved entity (ticker / CIK / UEI / LEI)        ← entity resolver (built)
      → SEC capex disclosure (EDGAR)                    ← demand signal, AI silo
      → power interconnection queue filing (ISO/LBNL)   ← energy silo
      → DoD program / NDAA line (Congress.gov)          ← defense silo
      → news corroboration (GDELT, link-only)           ← confidence weight
```

We already have the entity resolver and `entity_mentions` on every record. The missing piece
is **`entity_edges`** as a first-class, populated structure (it exists as a table per the
security audit, but nothing meaningfully fills it cross-domain yet). **Recommendation:** make
cross-domain edge construction an explicit pipeline stage, not a byproduct. That is the moat,
and it's what justifies a subscription over "I'll just ask an LLM."

This also argues for **cross-desk briefs** (or at least a cross-desk "convergence" section)
as a premium differentiator — see open question Q4.

---

## 6. Finding 5 — GDELT's real, narrow role

GDELT is genuinely valuable but only for what it's good at, and the notes oversell it:

- ✅ **Use it via BigQuery's 1 TB/mo free tier on the *partitioned* GKG table** with
  `_PARTITIONTIME` pruning (all three model answers converge on this — it's correct and the
  cost math holds for a daily windowed pull).
- ✅ **Use it as the discovery/co-occurrence layer** feeding the entity graph (which tracked
  entities are spiking, where).
- ⚠️ **Do not treat GDELT theme tags as reliable classification** — coverage for newer terms
  ("AI data center", "GPU cluster") is uneven; pair theme codes with entity/keyword matching
  (Claude's discovery-query trick to learn which codes actually fire is the right move).
- ⛔ **Do not cite GDELT article text as a brief claim** — `DocumentIdentifier` is a
  copyrighted third-party URL. Link + short quote only (§6 license class `scrape_gray`).
- ⛔ **Do not poll it every 15 minutes for a daily product.** A once- or twice-daily windowed
  BigQuery pull is enough and keeps you deep inside the free tier.

GDELT is a *radar*, not a *source of record*. Treat it accordingly and it's nearly free and
genuinely useful; treat it as the spine and it becomes your biggest cost and licensing
liability.

---

## 7. Finding 6 — Licensing is an architectural constraint, not a footnote

This is the most under-weighted point in the raw notes and the most important for a **paid**
product. "Free to access" ≠ "redistributable in a paid subscription." `DATA_SOURCES.md`
already defines `license_class` (`public_domain` / `licensed` / `scrape_gray`) — we should
**enforce it in code**, on `NormalizedRecord`:

- Every adapter declares its `license_class`.
- The synthesis stage may **quote/republish** only `public_domain` text; `licensed` and
  `scrape_gray` may be **cited and linked** and synthesized-from, but their raw text must
  never appear verbatim in a published brief body.
- The citation-faithfulness eval should be license-aware: a claim cited to a `scrape_gray`
  source must be a *link*, not a quoted block.

Sources flagged in the notes that need explicit commercial-license review **before** they
enter the paid product: **ACLED, Global Trade Alert, IEA datasets, The Lens, commercial news
APIs.** Government data (USAspending, SEC EDGAR, EIA, FRED, SAM.gov, Congress.gov) is both
free *and* freely redistributable — which is exactly why the free-first stack is also the
*safe* stack. The licensing posture and the cost posture and the moat all point the same
direction: **lead with public-domain structured data.**

> **Candidate decision (D0xx):** *`license_class` is a required field on every adapter and is
> enforced at synthesis: only `public_domain` text may be republished; everything else is
> link-and-cite only.*

---

## 8. Finding 7 — Source reliability / provenance tiering

For a decision-grade product, not all corroboration is equal: a DoD contract announcement
(primary) outweighs a GDELT-tagged blog (tertiary). We should carry a **source tier /
reliability weight** so synthesis and materiality scoring can prefer primary sources and so
confidence reflects *who* is saying it:

- **Tier 1 — primary record:** the agency/filer itself (USAspending, EDGAR, EIA, NRC, FERC,
  Congress.gov). Citable as fact.
- **Tier 2 — authoritative secondary:** SIPRI, OECD.AI, Ember, OWID, established trade press.
- **Tier 3 — discovery/sentiment:** GDELT, general news, social. Weight, don't cite as fact.

This is a small schema addition (a `source_reliability` enum on the adapter/record) that pays
off in synthesis quality and in honest confidence scoring.

---

## 9. Proposed target architecture

Layered, reusing what's built (✅) and naming the gaps (❌). This refines the notes'
Aggregate→Normalize→Resolve→Score→Synthesize into something that fits our schema:

```
┌─ A. INGEST ─────────────────────────────────────────────────────────────┐
│  Scheduler (per-source cadence) ❌  →  Adapter.parse() ✅  →  raw_records  │
│  source_runs accounting ❌ · retry/backoff ❌ · content_hash dedup ✅(gate)│
└───────────────────────────────────────────────────────────────────────────┘
            ▼
┌─ B. NORMALIZE + LICENSE-TAG ─────────────────────────────────────────────┐
│  NormalizedRecord ✅  + license_class ❌  + source_reliability ❌            │
└───────────────────────────────────────────────────────────────────────────┘
            ▼
┌─ C. RESOLVE + LINK ──────────────────────────────────────────────────────┐
│  entity resolver ✅  →  populate entity_edges (cross-domain) 🟡 partial     │
└───────────────────────────────────────────────────────────────────────────┘
            ▼
┌─ D. CLUSTER + SCORE ─────────────────────────────────────────────────────┐
│  embedding dedup/cluster ❌  →  materiality ✅ + novelty ❌ + confidence ❌  │
│  (this is where a "signals/events" abstraction may belong — see Q5)        │
└───────────────────────────────────────────────────────────────────────────┘
            ▼
┌─ E. SYNTHESIZE ──────────────────────────────────────────────────────────┐
│  cheap triage → top-N → premium synthesis (D006) → citation eval ✅         │
│  license-aware citations ❌                                                 │
└───────────────────────────────────────────────────────────────────────────┘
```

The biggest *new* architectural question is whether to introduce a **`signals` / `events`**
layer between normalized records and briefs (the notes propose it). Today we go
`normalized_records → brief`. A deduplicated, scored, cross-source **event** object would be
the natural home for cross-domain edges, novelty, and confidence — and the natural unit for
"the same story across 20 outlets." See Q5.

---

## 10. Recommended source-onboarding sequence (cost-aware)

Given the moat (entity graph) and the cost lever (structured-first), the order that buys the
most product per dollar/effort:

1. **Build the runner** (§3) — unblocks everything; pick USAspending (already built) as the
   first live source to prove the loop end-to-end with fresh data.
2. **SEC EDGAR** (full-text search + company-facts + **Form 4 / 13F / 13D-G**) — 🟢 free,
   keyless. *Cross-cuts all three silos* (hyperscaler capex = AI demand engine,
   defense-contractor fundamentals, energy capex) **and** is the richest free **smart-money /
   investment-signal** vein (Q4/audience note). Highest leverage of any single add; also
   strengthens the entity graph (CIK ↔ ticker already in the resolver).
3. **EIA Open Data + interconnection-queue data (ISO/LBNL)** — 🟢 free. Lights up the Energy
   desk *and* the AI-power-demand convergence story (the single best cross-silo narrative,
   which the Q4 convergence brief now showcases).
4. **Global procurement + defense** — 🟢 free/public: **EU TED**, **UK Contracts Finder**,
   **SIPRI** (arms/expenditure), **SAM.gov** (request the API key now — lead time). Delivers
   the Q2 global scope on the public-domain side. Pairs "what's being bid" (SAM/TED) with
   "what was awarded" (USAspending).
5. **Macro + market context** — 🟢 free: **FRED** (macro framing), **FINRA** short interest,
   **Finnhub free** (prices/calendar). Cheap reinforcement of the finance-forward audience.
6. **GDELT (keyless DOC 2.0 JSON API)** + curated global RSS — 🟢 the discovery/corroboration
   radar, added *after* the structured spine + signals layer exist so news has entities/events
   to attach to. (BigQuery deferred per Q6.)
7. **One cheap paid upgrade, revenue-gated:** FMP (~$19/mo) for clean prices + fundamentals +
   transcripts; optionally Quiver (~$10–50) for congressional trades — only once subscriptions
   justify it (Q3).

Defer (margin/licensing risk): ACLED, Global Trade Alert, IEA paid sets, satellite, premium
social. Everything in `DATA_SOURCES.md` Tier 3 stays deferred.

---

## 11. Schema implications (small, additive)

- `NormalizedRecord` (and the `raw_records`/`normalized_records` tables): add
  **`license_class`** and **`source_reliability`**. Both are cheap, both are load-bearing.
- A **`source_runs`** table for ingest accounting (cursor, last_success, counts, errors).
- Decide on a **`signals`/`events`** table (Q5) as the home for dedup-clusters + cross-domain
  edges + novelty/confidence.
- `entity_edges`: define the edge types we actually populate (e.g.
  `supplies`, `competes_with`, `powers`, `funds`, `regulates`) so cross-domain queries are
  meaningful rather than ad hoc.

None of these break the current pipeline; they're additive and can land incrementally.

---

## 12. Resolved decisions (settled 2026-06-14)

The open questions have been answered by the operator. These are now constraints, not
options, and should be ratified into `DECISIONS.md`:

| # | Decision | Consequence |
|---|----------|-------------|
| **Q1** | **Daily brief** cadence | Structured-first; ingestion cadence matched to daily publish (no 15-min polling). Cost ceiling bounded. |
| **Q2** | **Global** scope (consistent with the SITREP app) | Add global gov/procurement adapters over time; hold LLM cost flat via deterministic pre-filter + English-tag, not by limiting geography (see §12a). |
| **Q3** | **Minimal cost now**; paid data subs added later *if/when subscriptions grow* | Free-first stack only; FMP (~$19/mo) and any other paid source stay revenue-gated. |
| **Q4** | **Three desk briefs + a cross-domain convergence brief** (mirrors SITREP) | Convergence brief is a first-class product — the moat made visible. Adds synthesis complexity; justified by differentiation. |
| **Q5** | **Add the `signals`/`events` layer** | Deduplicated, scored event objects sit between `normalized_records` and briefs; home for cross-domain edges, novelty, confidence. Schema commitment accepted. |
| **Q6** | GDELT: **start with the keyless DOC 2.0 JSON API**; BigQuery only if/when deeper co-occurrence queries are wanted | No GCP account or billing setup required for Cycle 2 (see §12a for the BigQuery economics if we revisit). |
| **Q7** | **Fully autonomous publishing** (revisit only at significant scale) | No human-in-the-loop gate; the citation-faithfulness eval (Gate 5) remains the automated quality bar. No draft/approve state needed yet. |
| **Q8** | **Retain a hot trailing window** + permanent output archive (see §12a) | 14–30 day hot window for `normalized_records` + embeddings; prune/archive raw; keep `briefs` + `signals` indefinitely. |

**Audience note (finance-forward).** The operator wants strong coverage for *actionable
investment/finance ideas* — "more is better, within limits." This elevates the free
**smart-money** sources (SEC EDGAR filings + Form 4 insiders + 13F institutions + 13D/G
activists, FINRA short interest, FRED macro) in the onboarding sequence (§10). "Within
limits" = exhaust free smart-money sources before buying FMP/Quiver.

---

## 12a. Cost & storage economics (the basis for Q2/Q6/Q8)

**Global vs US — dollar differential ≈ $0.** Same infra. The real costs of "global" are
engineering time (more adapters) and *potential* LLM-token inflation from a bigger firehose —
both controlled by the runner + deterministic pre-filter (entity allowlist + theme codes +
`TAX_WORLDLANGUAGES_ENGLISH`), not by money. GDELT's own machine translation means
multilingual coverage costs ~$0 if we filter to English-tagged items rather than translating
raw text ourselves. Licensing is the only place global adds real future cost (ACLED, GTA, IEA)
— all deferred.

**GCP / BigQuery (Q6) — effectively $0/mo at our scale, but needs a billing-enabled account.**
Free tier is 1 TB query processing + 10 GB storage *per month*; a daily windowed pull against
`gdelt-bq.gdeltv2.gkg_partitioned` with `_PARTITIONTIME` pruning scans tens of MB to a couple
GB — <1% of free tier. Beyond free tier ≈ $6/TB scanned (irrelevant here). The only footgun is
an unpruned full-table scan (terabytes) — neutralized by a budget alert (~$1) + a custom query
quota + always querying the partitioned table. **Decision Q6 defers this:** use the keyless
**GDELT DOC 2.0 JSON API** for Cycle 2 (no account, no card, rate-limited but fine for radar);
revisit BigQuery only for deeper co-occurrence analytics.

**Supabase storage (Q8) — storage dollars are trivial; the vector index is the real limit.**
On Pro (~$25/mo): ~8 GB DB included (~$0.125/GB/mo after), ~100 GB object storage. Sizing:
- A normalized record + 1536-dim embedding ≈ **~10 KB**. Post-filter global volume of
  500–2,000 records/day ≈ **35–140 MB/week** — negligible against 8 GB.
- `raw_records` (pre-filter payloads) ≈ 50 MB/day ≈ 350 MB/week, and ~18 GB/yr **if never
  pruned** — that *would* exceed the included tier in months.
- The binding constraint is **not storage cost** — it's the **HNSW vector index**, which is
  memory-resident and pushes you to a larger (pricier) compute add-on as the embedded set
  grows, and slows queries.

**Retention policy (records this decision):**
- **Hot — `normalized_records` + embeddings: trailing 14–30 days.** Keeps the vector index
  small/fast; enough for dedup, clustering, recent-context RAG, regeneration.
- **`raw_records`: prune to ~14 days** (or archive older as compressed JSON to object storage
  if replay is ever wanted).
- **`briefs` + `signals`/`events`: keep indefinitely** — tiny (KB each), and they *are* the
  product's durable archive (also what the Pro paywall sells).

Net steady-state storage cost: a few dollars/month at most, dominated by compute sizing, not
bytes — which is exactly why the hot window is capped.

---

## 13. Concrete next steps (decisions settled — ready to build)

1. Ratify the candidate decisions into `DECISIONS.md`: **structured-first / news-secondary**,
   **license-class enforcement**, plus the Q1–Q8 settlements in §12 (daily, global, minimal
   cost, 3 desks + convergence, signals layer, keyless GDELT, autonomous publish, retention).
2. Build the **ingestion runner** (scheduler + `source_runs` + dedup) against the existing
   adapter contract; prove it with live USAspending data replacing the seeded fixtures.
   Apply the **14–30 day hot-window retention** (§12a) from day one.
3. Add **`license_class` + `source_reliability`** to the record schema and enforce
   license-aware citations.
4. Introduce the **`signals`/`events` layer** (Q5) + deliberate **`entity_edges`** population —
   the substrate the convergence brief (Q4) reads from.
5. Onboard **SEC EDGAR** (incl. Form 4 / 13F — finance-forward) as the second adapter
   (max cross-domain + smart-money leverage).
6. Add **EIA + interconnection queues**, then **global procurement (TED/UK/SIPRI/SAM)**.
7. Add **GDELT (keyless DOC API)** + RSS as the discovery/corroboration radar last.

The thread through all of it: *the cheapest pipeline, the most defensible pipeline, and the
highest-provenance pipeline are the same pipeline* — structured public-domain data as the
spine, an entity graph as the moat, news as radar, and LLM spend reserved for synthesizing
the few things that survive deterministic filtering.
