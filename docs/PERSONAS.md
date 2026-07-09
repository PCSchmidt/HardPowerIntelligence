# HPI Personas — the Phase-B ranking engine

**Status:** DRAFT 2026-07-09 · **Phase:** B0 (do-first; see [PHASE_PLAN.md](PHASE_PLAN.md)) · **Companion:** `MOCKUPS.md` (B5), `FRONTEND_SPEC.md` §9

## Why this exists

With a thin real-feedback pool you can't A/B your way to the right Phase-C hero surface.
These synthetic personas are the **ranking engine**: each points at a candidate surface, and
the Phase-C build target is decided by **which personas the real 8–10 Phase-B conversations
most resemble**. Personas rank the options; the real conversations validate or adjust the
personas. Nothing here is a commitment — it's an instrument for choosing *what to commit to*.

**How to use it (Phase B):**
1. Run the 8–10 warm/cold conversations (B2/B3) using each persona's **interview probes**.
2. After each, score how strongly the real person **resembles** each persona (0–3).
3. Tally resemblance → each persona casts its weight toward its **ranked surface** (below).
4. The surface with the most weight, triangulated against what people got visibly excited
   about, is the Phase-C C1 build target. Ties break toward **lower build risk**.

---

## The five personas

Each persona: who they are · the job · what they'd pay for · the "aha" moment that converts
them · the objection that kills it · three interview probes · the surface it votes for.

### P1 — Thematic hedge-fund analyst ("gets there before consensus")
- **Who:** buy-side analyst/PM at a thematic or multi-strat fund; covers the AI-power-demand →
  nuclear/utilities/grid chain across sectors.
- **Job:** spot cross-sector inflections *before* they're consensus and defend the thesis internally.
- **Pays for:** a convergence signal they can't get from single-sector tools, **plus provenance**
  to defend a call to their IC.
- **Aha:** "This entity just showed up on both the AI desk and the Energy desk in the same week,
  and here's the primary-source chain proving it." Convergence + citation in one view.
- **Kills it:** if it reads as recycled news they already saw on Bloomberg/The Diff; if the
  convergence link feels like a keyword coincidence, not a real relationship.
- **Probes:** (1) "Walk me through the last cross-sector call you made — how'd you find it?"
  (2) "What would you need to see to trust a convergence link enough to act on it?"
  (3) "Where does your current workflow lose the thread between sectors?"
- **Votes:** **A — Convergence Map** (entity/theme graph + timeline).

### P2 — Energy/infra PE / project-finance associate ("track the capital")
- **Who:** associate at an infra fund / project-finance shop; deploys or tracks deployment capital.
- **Job:** track capital formation — awards, FIDs, financings, and the policy that gates deployment.
- **Pays for:** structured **capital-flow + regulatory** tracking they'd otherwise assemble by hand.
- **Aha:** "$X of *actually-tracked* capital moved into this theme this month, here are the deals,
  and here's the catalyst calendar for what's next." (The D138 tracked-vs-projected split is exactly
  the honesty this persona demands — a market projection in the total would discredit the whole tile.)
- **Kills it:** double-counting, projections dressed as committed capital, or stale award dates
  (all three now addressed — D137/D138 — which is why this persona is newly credible).
- **Probes:** (1) "How do you currently size capital moving into a theme?" (2) "What's your source
  of truth for FIDs/awards, and what does it miss?" (3) "How far ahead do you need catalyst visibility?"
- **Votes:** **B — Capital & Catalyst Dashboard.**

### P3 — Corp-dev / strategy at a prime or energy major ("watch the board")
- **Who:** corporate development / strategy at a defense prime or energy major.
- **Job:** competitive intel, M&A radar, supply-chain moves around specific competitors/targets.
- **Pays for:** **entity-centric monitoring** — follow a named set of companies and get everything
  material about them, cited.
- **Aha:** "I follow these 12 entities and HPI hands me every award, filing, and convergence move
  they make, with the source." Entity360 + a watchlist that actually alerts.
- **Kills it:** coverage gaps on their specific entities; alerts that fire on noise.
- **Probes:** (1) "Whose moves do you track, and how?" (2) "What's the cost of finding out a week
  late?" (3) "What makes an alert worth keeping vs. muting?"
- **Votes:** **A — Convergence Map** (entity-centric slice) + follow-alerts (a Phase-D pull).

### P4 — Policy / think-tank / gov-BD researcher ("cite the record")
- **Who:** analyst at a think tank, policy shop, or the BD/strategy arm of a gov contractor.
- **Job:** authoritative, **cited** tracking of programs, appropriations, and regulatory action.
- **Pays for:** **provenance + primary-source linkage** — the ability to trace every claim to the record.
- **Aha:** "Every line is clickable to the filing/notice/award it came from, and there's a policy
  timeline + catalyst calendar of what's coming." Provenance *is* the product for this persona.
- **Kills it:** any hallucinated or uncited claim — one is disqualifying; thin regulatory coverage.
- **Probes:** (1) "How much of your day is spent re-finding the primary source for a claim?"
  (2) "What would make you trust an aggregator's citations?" (3) "Which programs/dockets do you live in?"
- **Votes:** **B — Capital & Catalyst Dashboard** (provenance-forward + policy timeline variant).

### P5 — Generalist macro / family-office investor ("a trustworthy daily read")
- **Who:** generalist investor, family-office principal, or exec who wants the hard-power complex
  without drowning in it.
- **Job:** one trustworthy daily read on Defense∩AI∩Energy with the "so what" made explicit.
- **Pays for:** the **curated convergence narrative** + judgment — not a data terminal.
- **Aha:** "In 90 seconds I understand what changed across the whole complex and why it matters."
  Editorial BLUF, least graph, most narrative.
- **Kills it:** feels like a data dump or homework; not obviously worth more than a free newsletter.
- **Probes:** (1) "What do you read daily to stay oriented, and what's missing?" (2) "Do you want to
  *explore* the data or be *told* the takeaway?" (3) "What would make this a paid habit vs. a nice-to-have?"
- **Votes:** **C — Narrative Convergence Homepage.**

---

## Candidate surfaces (the 5 bundles → 3 mockable archetypes)

The seed table listed five surface *bundles*; they collapse into three **hero mechanics**, which
is what B5 mocks. Each desk landing page is the same brief underneath — the archetype is what leads
*above* the read (the "BLUF + big picture" layer that's missing today).

| Archetype | Hero mechanic | Serves | Build risk | Leans on |
|---|---|---|---|---|
| **A — Convergence Map** | Interactive entity/theme graph: nodes = entities, edges = cross-desk co-appearance; click → Entity360 + cited appearances | P1, P3 | **High** (real interactive viz, data density, mobile-degrade) | the entity-resolution graph (the moat, D091/D092) |
| **B — Capital & Catalyst Dashboard** | Structured tiles above the read: tracked-capital total + top deals (magnitude), catalyst calendar, provenance-forward source strip | P2, P4 | **Medium** (mostly composition of data we already compute) | tracked-vs-projected (D138), amounts, citations, published_at |
| **C — Narrative Convergence Homepage** | Editorial "state of the desk" BLUF (2–3 sentences) + a few glanceable tiles, minimal graph | P5 | **Low** (closest to today's reader) | the existing BLUF + at-a-glance ledger (D084) |

**Reading the spread:** A is the "wow" differentiator but the riskiest and most expensive; C is the
safe, cheap extension of what exists; B sits in the middle and is the one most *unlocked by recent
work* (D137/D138 made the capital numbers honest enough to headline). The Phase-B conversations
decide which mechanic people actually lean toward — do they want to **explore** (A), **track** (B),
or be **told** (C)?

## Ranking worksheet (fill during Phase B)

```
Per interview: resemblance score 0–3 to each persona → weight to that persona's surface.

           P1→A   P2→B   P3→A   P4→B   P5→C
Convo 1
Convo 2
...
Convo 10
─────────────────────────────────────────────
Surface totals:   A = ΣP1+ΣP3    B = ΣP2+ΣP4    C = ΣP5
Phase-C target = argmax(surface totals), ties → lower build risk (C < B < A).
Triangulate against: which mock did people physically react to in B5?
```

---

*Disposable-discovery discipline: these personas and the B5 mocks are validation instruments.
Committed design spec for the chosen surface is deferred to Phase-C entry (FRONTEND_SPEC.md §9,
PHASE_PLAN.md C1). Do not build the hero surface before the B decision gate.*
