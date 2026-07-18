# Convergence Graph — build plan

**Status:** **§1–§5 SHIPPED + DEPLOYED (D146–D153).** The full arc is live at `/graph`: §1 edge layer,
§4 name-gazetteer coverage lift, §2 graph API, §3 interactive hero viz, plus the brand redesign (D151),
edge-evidence hover — the cited stories behind a connection (D152), and **§5 the AWARDED federal-funding
overlay** (D153: agencies as `gov_agency` nodes, 121 agency→company edges from USAspending, toggleable).
The same-company self-edge artifact is suppressed (D150). Graph is **9 CONVERGES_WITH edges (8
cross-desk)** + the funding overlay today, and compounds as briefs accrue. **Remaining/optional:**
LLM-extracted company↔company semantic edges (SUPPLIES/TRANSACTED — a separately-eval'd pass), full
entity-dedup, gazetteer stopword tuning, desk-anchored layout. The Phase-C
Archetype-A hero surface
(the interactive entity/theme graph) and its foundation. **Companion:** [PERSONAS.md](PERSONAS.md) (A
serves P1/P3), `MOCKUPS.md` (B5), [PHASE_PLAN.md](PHASE_PLAN.md).

> **§1 → §4 story (2026-07-16/17) — how the graph went from starved to legible.** §1's first live run
> produced **exactly 1 edge from 215 co-appearances**: 212 of 213 pairs appeared once, because **most
> items linked ≤1 entity** — the linker was identifier-only (EDGAR/USAspending carry a ticker/CIK/UEI;
> feeds/GDELT/arXiv emit none), so there was rarely a *pair* to connect. That re-sequenced the track:
> §4 (name linking) became the blocker, not a parallel nicety. §4 (D147) matched known multi-word
> company names in item text (precision-guarded: multi-word only, word-boundary, ambiguity-drop, plus a
> document-frequency stopword pass that caught generic collisions like the phrase "quantum computing"
> vs the company QUBT). Result: item linking **24% → 31%**, edge-able items **14 → 41**, and the graph
> **1 → 10 edges (9 cross-desk)** — led by **Ramaco Resources ── USA Rare Earth spanning
> Defense∩AI∩Energy**, the trilateral thesis, now computed. It compounds further as briefs accrue (the
> daily `graph` job) and as §4's stopword list is tuned. **New order: §1 ✓ → §4 ✓ → §2 API → §3 viz.**

> **Framing (2026-07-16 decision).** Build cost is not the operator's binding constraint (abundant
> time/tokens; the build has learning + portfolio value regardless of the commercial outcome), so
> the usual "don't build the hero surface before the B gate" caution is relaxed. The two disciplines
> that survive: (1) keep the B2 *measurement* honest — a polished graph's "wow" is not demand;
> validate willingness-to-pay on behavior + the cold cohort, not demo reactions; (2) don't let the
> fun build starve the commercial-validation critical path (payments → B3). Build order below is
> therefore **craft-driven** (data before render), not a hedge against waste.

---

## Current state (verified 2026-07-16)

| Layer | State |
|---|---|
| **Nodes** (`entities`) | **8,151** — rich. Resolved + minted from EDGAR/USAspending identifiers (D091). Includes some SPAC/shell noise. |
| **Edges** (`entity_edges`) | **0.** Table + schema exist; **no producer code anywhere** (grep confirms only migration SQL references it). The compounding clock has not started. |
| **Item→entity links** (`brief_items.entity_ids`) | **270 / 1,097 items (~25%).** |
| **Cross-desk signal** | Real and on-thesis *today*: Energy Fuels, RealLoys, Comstock, Nova Minerals (3 desks), Centrus (2). Rare-earth + nuclear-fuel names spanning Defense/AI/Energy — the convergence thesis, uncomputed. |

**Why only 25% linked (the ceiling).** `engine/entity/linker.py` is **identifier-based**: it links an
item only when its source record carries a ticker/CIK/UEI (EDGAR, USAspending) to resolve or mint on.
News (feeds — now the biggest source), GDELT, and arXiv items carry no such identifier, so they go
unlinked. This is a deliberate precision-first choice (an ambiguous name is left unlinked rather than
risk a wrong ticker), not a bug — but it caps graph density. Lifting it is a separate workstream (§4).

---

## The architectural fork (decide first)

`entity_edges.edge_type` has a CHECK with 15 **semantic** relationship types — `AWARDED`, `SUPPLIES`,
`COMPETES_WITH`, `EXPOSED_TO`, `RUNS_PROGRAM`, … — and **no co-occurrence type.** So the original design
envisioned a true *relationship* knowledge graph, not statistical co-appearance. Two ways to fill it,
serving two different jobs:

- **Co-appearance / convergence edges (thematic).** "These entities recur together across desks."
  Computable *now* from `entity_ids`. This is what a **Convergence Map renders** — the cross-desk
  clustering that is literally the thesis. Doesn't fit the current CHECK → needs an additive migration
  to add a `CONVERGES_WITH` type (same pattern as the D143 taxonomy widening). Weakly semantic, so it
  lives or dies on good weighting/decay/pruning (below), or it becomes a hairball.
- **Semantic edges (structural).** "Company X was AWARDED contract Y; supplies Z." Extracted from the
  structured data (USAspending award → `AWARDED`; EDGAR → `FILES_AS`/`HAS_SECURITY`). Higher fidelity,
  matches the moat vision, no schema change. More work (per-type extraction). This is the **node-detail**
  an analyst drills into, not the convergence view itself.

**Recommendation:** they're complementary, not either/or. The **convergence map needs co-appearance
edges** → build those first (§1). Semantic edges are a richer node-detail enrichment → later (§5). Ship
the thing that renders the thesis; deepen it after.

---

## §1 — Edge computation job (the foundation; first concrete build)

A backend job that computes cross-desk co-appearance edges from `entity_ids` and persists them. This is
the piece without which no graph renders, and the piece whose design decides whether *time compounds
signal or noise* (per the 2026-07-16 discussion — the compounding is real but only if built well).

**Design decisions baked in from the start (not retrofitted):**
- **Weight = co-appearance frequency × recency decay.** A pair seen once is weak (coincidence); seen
  repeatedly over weeks it's real. Recent convergence must dominate stale — for an investment product a
  convergence *this month* outweighs one from last spring. Use the `valid_from`/`valid_to` bitemporal
  columns the schema already carries; store weight/desk-overlap in `properties` (jsonb).
- **Confidence threshold prunes the coincidental.** Below a floor, an edge is noise — drop it, don't
  render it. This is the anti-hairball guard; without it the graph gets denser but *less* legible over time.
- **Cross-desk emphasis.** An edge where the two entities' desks differ (Defense↔Energy) is the
  convergence signal; same-desk co-appearance is ordinary. Score cross-desk higher.
- **Idempotent + incremental.** Recompute/upsert as briefs accrue (mirror the linker's best-effort,
  post-transaction pattern so it can never dark a brief).

**Deliverable:** `engine/engine/entity/graph_builder.py` (or similar) + a `CONVERGES_WITH` migration +
tests (golden co-appearance fixtures; weighting/decay/pruning correctness). Runs post-brief or as a
periodic job. **Feedback-independent, valuable regardless of archetype** (edges also power "related
entities" + convergence detection). ~1–2 gates.

## §2 — Graph API endpoint

Serve nodes + weighted edges to the web, filtered (by desk, time window, min-confidence, top-N by
weight so the payload isn't the whole 8k-node graph). FastAPI, reads `entity_edges` + `entities`.
Pagination/limits matter — a graph viz needs a *curated* subgraph, not the firehose. ~1 gate.

## §3 — The visualization (Archetype A, the sizzle)

Interactive entity/theme graph: nodes = entities, edges = convergence, click → Entity360 + cited
appearances (which already exist). This is the hero surface. Real build risk lives here (interactive
viz, data density, mobile degradation) — hence data-first. Library choice (e.g. a force-directed graph
lib, inlined per the artifact CSP constraints if ever shown as an artifact) is a §3 decision. ~2–3 gates.
**Discipline:** show it fully in demos, but read warm "wow" as *story-lands/impressive*, not as demand.

## §4 — Coverage lift (break the 25% ceiling) — parallel/after v1

News/GDELT/arXiv items are unlinked because they carry no identifier. To bring them into the graph:
run **NER on item text** → resolve mentions **by name** (the resolver's trigram path already exists)
against the reference set, precision-guarded. Higher effort + precision risk (wrong-entity links are
worse than no link). **Do after §1 proves the concept on the structured 25%** — which already contains
the highest-value nodes (award/filing companies). Don't block v1 on this.

## §5 — Semantic edges (node-detail depth) — later

Extract the schema's real relationship types (`AWARDED` from USAspending recipient↔agency, `FILES_AS`
from EDGAR, etc.). Turns the graph from "what converges" into "how they're actually related." The
knowledge-graph moat's deep end. Sequence after the convergence map ships.

---

## Suggested order

**§1 edge job → §2 API → §3 viz**, with **§4 coverage** and the **payments track** running in parallel.
§1 is the immediate next concrete piece: entirely feedback-independent, it's the foundation everything
else needs, and its weighting/decay/pruning choices are what make the moat compound instead of clog.
The virtuous cycle to keep in view: revenue (payments) → paywalled sources → richer records → more
entities + denser edges → better graph. The graph moat compounds with *time*; the source moat compounds
with *revenue* — which is why both tracks run together.
