# Philosophy

Why Hard Power Intelligence exists, what it is (and isn't), and the principles that
govern how it's built.

---

## 1. The engine thesis

HPI is a finance application of a general pattern: an **intelligence-production
engine**.

> Scrape many disparate public sources → normalize → multi-model LLM synthesis on a
> cheap waterfall → emit a high-status, recognizable professional format (the BLUF
> briefing) → deliver as in-app cards plus a polished PDF → run on a cadence with
> **one shared output served to all users**, so marginal cost stays near zero.

The product is **not the data** — most of it is free and public. The product is the
**aggregation + synthesis + format moat**: repackaging a commodity into something
that feels like an institutional work-product. The strategic question HPI answers is:

> *Which high-status financial work-product can you manufacture from scattered public
> data, on a cadence, for an identifiable buyer who already values time saved?*

The answer HPI bets on: a daily, source-grounded intelligence brief at the
convergence of the three strategic build-outs of this decade — **AI infrastructure,
next-generation defense, and energy** — sectors that are information-heavy,
source-fragmented, and moved by public events most readers never have time to track.

---

## 2. What HPI is — and is not

| HPI is | HPI is not |
|--------|------------|
| A recurring **research and reporting** product | An AI stock picker or trading-signal app |
| **Graded, source-attributed** synthesis (every item shows its basis) | A chatbot that answers from memory |
| A **publication** (general, not personalized) | A robo-advisor or personalized portfolio tool |
| **"What changed since yesterday"** intelligence | A static one-off report |
| A **wide net** over on-thesis public information | A reseller of expensive licensed feeds |

This framing is deliberate. The weakest part of AI-finance is hallucinated
recommendations; the strongest is information compression, change detection, source
linking, and report generation. HPI leans entirely into the latter.

---

## 3. The moat

Three things, in order of durability:

1. **The transmission layer (entity-resolution graph).** The unique engineering is
   mapping a raw event to the investable security and the thesis —
   `legal entity ↔ ticker ↔ CIK ↔ government contractor ID (UEI/DUNS) ↔ subsidiaries
   ↔ program`. No vendor sells this mapping for these sectors; building it is the
   product. It also enables second-order insight (e.g., AI capex → power/cooling
   suppliers → utilities) that commodity tools cannot surface.

2. **Graded provenance and a published accuracy bar.** Every item shows its **basis
   and confidence** — confirmed (primary record, cited), reported (attributed
   third-party), HPI analysis (our synthesis/inference), or speculative (early
   signal) — so the reader weighs it with the estimative transparency real
   intelligence analysis uses. Grounding is shown as *transparency about the basis*,
   never used as an admission filter that withholds important-but-not-pristinely-
   citable signal. The one hard line is **no fabrication**: an eval harness flags
   invented specifics before publish. Publishing this accuracy methodology turns the
   industry's biggest weakness (hallucination) into HPI's differentiator.

3. **Judgment over a wide intake — not institutional origin.** HPI casts a wide net
   across on-thesis AI/defense/energy information — any development with a linkable
   source is fair game — and the value is the synthesis, foresight, and compounding
   entity graph over that intake, *not* the .gov origin of a citation. Public primary
   records (USAspending, EDGAR, EIA, NRC, Congress.gov, BIS) stay the backbone and a
   real cost advantage, but they are the strongest *tier* of evidence, not the only
   admissible kind.

---

## 4. Design principles

1. **Shared output, near-zero marginal cost.** One brief per desk serves everyone.
   Personalization is *filtering and reordering* the shared brief by a user's
   follows — never per-user regeneration. This preserves both the cost model and the
   publication (non-advice) posture.

2. **Provenance is architecture, not UI.** Records carry source URL + timestamp at
   ingestion. Citations are guaranteed downstream because they're guaranteed at the
   source.

3. **Attribute, don't exclude.** Numbers come from structured fields verbatim; prose
   brings synthesis and clearly-hedged inference. Rather than dropping what isn't
   airtight, every item is graded and attributed so its basis is visible to the
   reader; the only bar enforced before publish is **no fabricated specifics**.
   *(The epistemic-framing layer implementing this is rolling out — primary-desk
   routing D097 and the attribution taxonomy D098 have shipped; the publish path is
   moving from suppress-under-grounded to keep-and-label.)*

4. **Cost discipline by default.** A model waterfall (cheap models for
   extraction/clustering, the strong model only for final synthesis), aggressive
   caching, and a budget guard keep the run cost low — the basis for an affordable
   price and profitability at a small number of subscribers.

5. **Free-first, paid-later.** Build on the free public stack that is both the
   credibility moat and the safe legal lane; add paid data only when subscribers fund
   it.

6. **One vertical deep before three shallow.** Launch the Defense desk fully; expand
   to Energy and AI-Infrastructure once the format and engine are proven.

---

## 5. Regulatory posture

HPI is a **general publication**, not personalized advice. It sits in the publishers'
exemption lane to the Investment Advisers Act: it reports on sectors and events, never
"what *you* should do with *your* portfolio."

Practical consequences baked into the design:

- No buy/sell recommendations, no personalized portfolios, no trade execution.
- Prominent "informational research, not investment advice" disclaimers.
- Personalization stops at filtering/ordering shared content by followed entities.

*This is a product-design posture, not legal advice; a real legal opinion should be
obtained before launch.*

---

## 6. Engineering governance

HPI is built under **Meridian**, an agent-harness framework enforcing a gate-by-gate
workflow: each gate requires its artifacts and an independent evaluation before work
proceeds. HPI is also a Meridian **dogfooding** vehicle — a full-stack web app whose
core is an ML/RAG eval pipeline, which exercises Meridian's composable gate DAG
(`fullstack-web` + `ml-research` gates composed into one). Friction found while
building HPI feeds back into Meridian's refinement.
