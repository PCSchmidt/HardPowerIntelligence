# Revisiting D055 / Q6 — BigQuery GDELT as a Primary Source, Plus Unlisted Sources Worth Adding

> Companion to [`docs/DATA_ARCHITECTURE_ANALYSIS.md`](../docs/DATA_ARCHITECTURE_ANALYSIS.md) and
> [`DECISIONS.md`](../DECISIONS.md) D055. Purpose: argue for **reopening** two settled
> decisions — the GDELT keyless-API-over-BigQuery call (Q6) and the implicit assumption that
> the current source list gives the AI and Energy desks enough material to publish reliably —
> on the operator's read that current depth/breadth is insufficient. This is a counter-argument
> to be weighed, not a directive; it ends with concrete next steps sized for a build session.

---

## 0. Start with the mechanism, not the philosophy

Before re-arguing GDELT in the abstract, it's worth being precise about *why* depth feels
thin today, because the cause is mechanical and traceable in code, not just a matter of too
few sources in a doc.

**`engine/engine/brief/materiality.py`** scores every candidate record as:

```
score = authority*0.25 + novelty*0.30 + magnitude*0.20 + importance*0.15 + corroboration*0.10
```

`source_weights` in `engine/engine/settings.py` fixes `gdelt` at **0.5**, against
`usaspending` at **0.9** and `edgar` at **0.85**. A fresh GDELT item with no `amount_usd`
(true for nearly all news) caps near `0.5*0.25 + 1.0*0.30 + 0 + 0.5*0.15 ≈ 0.55`. A fresh
USAspending award routinely scores `0.9*0.25 + 1.0*0.30 + 0.7*0.20 + 1.0*0.15 ≈ 0.86`.
Against `brief_max_items = 8`, GDELT-weighted items are **structurally crowded out**
whenever any structured competition exists — which means "GDELT is radar, not spine" isn't
just a stated philosophy (D055), it's enforced almost to the point of irrelevance by the
scoring math itself.

The sharper problem: **`engine/engine/brief/generator.py`** raises a hard `RuntimeError` if
fewer than `brief_min_items` (3) candidates clear `materiality_threshold` (0.35) inside the
48-hour window. Today, the AI desk's candidate pool is effectively **arXiv probes + a few
USAspending grant probes + EDGAR full-text hits**; the Energy desk is similarly thin. Both
desks are documented in the README as "wired and awaiting their first published run" — which
is the visible symptom of this candidate-pool problem, not a coincidence.

**Conclusion:** the depth complaint is real and it has two separate fixes, not one:

1. GDELT's *role* should expand — not to become a cited source (the licensing reasoning in
   D055/§6-7 of the architecture doc was correct and shouldn't change), but to become a
   genuinely useful **entity-spike and co-occurrence detector**, which BigQuery can do and
   the keyless DOC 2.0 API structurally cannot.
2. The AI and Energy desks need **more structured, primary-record sources**, independent of
   the GDELT question, because that's what actually prevents the `RuntimeError` and is most
   consistent with D055's own stated preference for structured-first data.

---

## 1. Part 1 — The case for BigQuery GDELT over the keyless DOC 2.0 API

Q6 (`DECISIONS.md`, `docs/DATA_ARCHITECTURE_ANALYSIS.md` §12a) chose the keyless DOC 2.0 JSON
API for Cycle 2, deferring BigQuery "until deeper co-occurrence analytics are wanted." The
argument here is that **that condition has already arrived** — the convergence-graph moat
(D055's own stated differentiator) needs exactly the kind of aggregate, per-entity,
per-theme signal that only BigQuery's GKG and Events tables can produce.

### 1.1 What the DOC 2.0 API gives you vs. what BigQuery GKG gives you

The keyless API returns article-level hits: title, URL, a single tone score, language, a
handful of fields. It answers "does an article matching this query exist." It does not
answer "is this entity's media mention frequency spiking relative to its baseline," "which
two themes are increasingly co-occurring this week that weren't last week," or "what is the
actual emotional/contextual signature of coverage around this entity" — all of which require
either many sequential API calls stitched together client-side, or a single grouped SQL query
against GKG.

Specifically, BigQuery's `gdelt-bq.gdeltv2.gkg_partitioned` exposes per-article:

- `V2Organizations` / `V2Persons` — the actual entity-mention fields, aggregable across a
  rolling window. This is the direct input to `entity_edges` — D055's own stated moat —
  in a way the DOC API's title/URL-only response cannot feed.
- `V2Themes` — thousands of theme codes, joinable and groupable, vs. one-query-per-theme
  through the DOC API.
- `V2GCAM` — a ~24-dimension emotional/contextual scoring system (fear, anger, optimism,
  economic sentiment, etc.), a materially richer signal than the DOC API's single tone value.
- `V2Locations` — structured geo data for free, no separate geocoding step.

And `gdelt-bq.gdeltv2.events_partitioned` (a separate table the DOC API has no analog to at
all) carries **Goldstein scale** (conflict/cooperation intensity, -10 to +10) and actor-pair
fields per event — directly useful for the Defense desk's geopolitical-tension framing (e.g.,
a measurable spike in `MILITARY_ASSISTANCE` or `THREATEN` event codes between a tracked
country pair) in a way no article-level news API replicates.

### 1.2 The product unlock, concretely

| Capability | DOC 2.0 keyless API | BigQuery GKG/Events |
|---|---|---|
| "Does an article about X exist" | ✅ | ✅ |
| "Is mention-of-X spiking vs. its 30-day baseline" | ❌ (would require manual aggregation across many calls) | ✅ single grouped query |
| "Which themes are co-occurring with tracked entities this week" | ❌ | ✅ single query, joins `V2Themes` × `V2Organizations` |
| Feed `entity_edges` with an aggregate "heat" signal | ❌ practically | ✅ — this is what the moat thesis (D055 §5/Finding 4) actually needs |
| Geopolitical tension scoring for Defense desk framing | ❌ | ✅ via Events table Goldstein scale |
| Rich emotional/contextual signal (24-dim GCAM) vs. single tone score | ❌ | ✅ |

The DOC API was scoped (correctly, at the time) as "enough for radar." The argument now is
that the convergence-graph product needs more than radar from this layer — it needs the
aggregate signal that tells the rest of the pipeline *where to look*, and that's a BigQuery
job, not a DOC API job.

### 1.3 The cost case still holds — this was already proven in §12a

Nothing here changes the cost math your own analysis already did:

- Free tier: **1 TB query processing/month**. A daily, `_PARTITIONTIME`-pruned pull against
  the partitioned GKG **and** Events tables scans tens of MB to low single-digit GB per
  run — comfortably under 1% of free tier even run daily against both tables.
- The only real footgun is an unpruned full-table scan; neutralize with a GCP budget alert
  (~$1 threshold), a custom query quota, and a hard rule that every query goes through the
  `_partitioned` table, never the bare `gkg`/`events` table.
- The one real friction Q6 weighed was GCP service-account auth (a Fly.io secret, scoped to
  BigQuery read-only) vs. the DOC API's zero-setup. That's a one-time setup cost. Given that
  two of three desks are at risk of not publishing on a given day, trading a half-day of GCP
  auth setup for a materially richer entity-spike/co-occurrence signal is a good trade.

### 1.4 What does NOT change — guardrails to carry forward

This is an argument for expanding GDELT's **role**, not for relaxing the citation/licensing
posture that D055 and the architecture doc's §6-7 got right:

- GDELT data is still **never a cited fact** in a published brief body. `DocumentIdentifier`
  remains a third-party copyrighted URL — link-only, `scrape_gray` license class, exactly as
  already specified.
- GDELT's `source_weights` entry should **stay low** (0.5 or lower) for *materiality scoring
  of GDELT-sourced candidate records* — that's correct, because GDELT is still not a primary
  record. What changes is that BigQuery's aggregate output (entity-spike scores,
  theme-co-occurrence counts) becomes an **input to corroboration/confidence weighting and to
  `entity_edges` construction**, not a new class of citable record competing with USAspending
  or EDGAR for `brief_max_items` slots.
- Cadence stays daily-aligned, not 15-minute — that reasoning (§4, §6 of the architecture doc)
  doesn't change just because the table changed.

---

## 2. Part 2 — Sources not currently on the roadmap, scored against actual desk gaps

These are absent from both `general_data_source_notes.md` and `docs/DATA_SOURCES.md`. Listed
against the desk each most directly unblocks, since desk-starvation (not source-count) is the
real constraint.

### 2.1 Energy desk (currently thinnest)

- **NRC ADAMS / reactor status data.** Already named in `DATA_SOURCES.md` category H as a
  target but has no adapter. SMR licensing dockets and reactor status updates are slow,
  lumpy, and unambiguously primary-record — exactly the profile structured-first scoring
  rewards. Likely higher per-engineering-hour leverage than the GDELT work above, *for this
  desk specifically*.
- **ISO/RTO open data portals — PJM, ERCOT, CAISO, MISO.** Mentioned only in passing
  (`docs/DATA_ARCHITECTURE_ANALYSIS.md` §5's graph diagram) as "power interconnection queue
  filing," with no adapter built. This is structured JSON/CSV, mostly free/keyless, and is
  the actual *evidence* behind the "AI buildout is driving grid demand" convergence story —
  the single best cross-silo narrative the architecture doc itself flags as the differentiator.
- **EIA-861 / EIA-930 hourly grid operating data.** A finer-grained extension of the EIA API
  already on the roadmap (category H) — granular enough to show *which regions* are seeing
  load growth, a genuinely differentiated data point.

### 2.2 AI desk

- **Epoch AI data exports.** Already referenced in `DECISIONS.md`'s later sharpening note
  ("Epoch AI + Ember + arXiv + Form D") as a known gap, never built. Structured, free, and
  tracks training-run/compute trends — Epoch has already done synthesis work that would
  otherwise require LLM triage of raw news, which is exactly the kind of pre-digested
  primary-ish record the structured-first philosophy should prioritize.
- **Hugging Face Hub API** (`/api/models`, `/api/papers/daily`). Free, keyless, gives a
  quantifiable proxy (download/like velocity deltas) for "what's heating up" in open AI
  research and tooling — cheaper to process than news triage and not currently listed
  anywhere in the source docs.
- **SEC Form D, via the EDGAR adapter already live.** Not a new source — an unbuilt extension
  of `engine/engine/adapters/edgar.py`. Already flagged in `DECISIONS.md` as the free proxy
  for private AI-infrastructure capital formation (Crunchbase/PitchBook being the paid
  alternative). Probably higher leverage than a new integration since the adapter and
  entity-resolution plumbing already exist.

### 2.3 Cross-desk, genuinely new

- **GitHub public API (events/trending).** Not present in any source doc. Release velocity
  and star growth on open robotics/autonomy repos (Defense∩AI), model-serving frameworks
  (AI), and grid-simulation tooling (Energy) is a free, structured "advancement" signal
  alongside arXiv. `api.github.com` is already an allowed egress domain.
- **Google Patents Public Datasets in BigQuery** (`patents-public-data`). If the BigQuery
  service-account setup above happens for GDELT, this dataset sits in the same project at
  zero marginal setup cost and supports the kind of aggregate trend queries (patent filing
  velocity by assignee/CPC code) that USPTO PatentsView's API-based access makes more
  expensive to replicate. Complements, doesn't replace, the already-listed PatentsView target.

---

## 3. Recommendation — what to actually change in D055/Q6

1. **Reopen Q6.** Replace "keyless DOC 2.0 API, BigQuery deferred" with: **build the BigQuery
   GKG + Events adapter now**, scoped explicitly to entity-spike detection and
   theme/co-occurrence signal feeding `entity_edges` and corroboration weighting — **not**
   to brief-citable records. Keep `source_weights["gdelt"]` low; the role changes, the
   citation posture does not.
2. **Treat AI/Energy desk thinness as the more urgent, separate problem.** NRC, ISO grid
   data, and Epoch AI are primary-record sources that more directly prevent the
   `brief_min_items` `RuntimeError` than richer news ever would, since news was never going
   to be a cited fact regardless of which GDELT access path is used.
3. **Sequence:** NRC + one ISO adapter (Energy desk unblock) and Epoch AI + Form D extension
   (AI desk unblock) are likely cheaper to build and higher-leverage *per desk* than the
   BigQuery migration. The BigQuery GDELT adapter is still worth doing, but for the
   entity-graph/convergence reason in §1, not as the fix for desk thinness.
4. **Schema/ops follow-through**, consistent with what `DATA_ARCHITECTURE_ANALYSIS.md` §11
   already flagged as needed regardless: `license_class` and `source_reliability` enforced on
   every adapter (including the new GDELT one), a GCP budget alert before the first BigQuery
   query runs, and `entity_edges` construction made an explicit pipeline stage rather than a
   byproduct — since that's the actual destination for the new BigQuery signal.

### Suggested build order for a session against this document

1. NRC adapter (Energy) — primary-record, mirrors the `usaspending.py`/`arxiv.py` probe
   pattern, unblocks the desk most at risk.
2. One ISO/RTO adapter (start with whichever of PJM/ERCOT/CAISO has the simplest open-data
   auth story) — direct evidence for the convergence narrative.
3. Epoch AI adapter (AI desk).
4. Form D extension to the existing EDGAR adapter (AI desk, private capital).
5. BigQuery GDELT adapter (GKG + Events), scoped to entity-spike scoring → `entity_edges`,
   explicitly *not* wired into `materiality.py`'s candidate-record path the same way
   USAspending/EDGAR/arXiv are.
6. GitHub API + Google Patents BigQuery dataset, lower priority, cross-desk advancement signal.