# Hard Power Intelligence

**Markets intelligence on the AI, defense, and energy build-out.**

Hard Power Intelligence (HPI) turns scattered public data — SEC filings, federal
contract awards, energy and macro releases, regulatory actions, and news — into
**cited, source-grounded BLUF intelligence briefings** for investors tracking the
three strategic build-outs reshaping global markets:

- **AI Infrastructure** — the multi-year compute build-out: chips, data centers,
  hyperscaler capex, and the power demand it creates.
- **Defense** — next-generation systems: drones and autonomy, space, directed
  energy, electronic warfare, and the rebuilding defense-industrial base.
- **Energy** — new-tech and dominance trends: nuclear (including SMRs),
  alternatives, the grid, R&D, and energy-security themes.

The name is a triple play on *power* — **hard power** (defense), **electrical
power** (energy), and **compute power** (AI) — the three forces this product tracks.

---

## What it is

HPI is a **recurring intelligence-production engine**, not a chatbot and not a
stock picker. On a cadence, it ingests disparate public sources, resolves every
mention to the investable entity behind it, and synthesizes a professional
**Bottom-Line-Up-Front (BLUF)** brief where **every claim links to its source**.
One shared brief per sector desk serves all subscribers, so the marginal cost of
another reader is near zero.

The product is positioned as **source-grounded research and reporting** — an
informational publication, not personalized investment advice.

> "An intelligence officer for the industries rebuilding national power."

---

## Why it exists

The data that moves these sectors — DoD contract awards, EDGAR filings, NRC
licensing, hyperscaler capex, export-control actions, energy data — is **public but
fragmented, slow to read, and disconnected from its market meaning**. Serious
investors don't lack data; they lack the time to aggregate it and the tooling to
connect a raw event to the security it affects. HPI does that aggregation,
connection, and synthesis on a cadence — and shows its work.

See [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md) for the full thesis.

---

## What makes it different

1. **The transmission layer.** HPI's core asset is an entity-resolution graph that
   links a raw event to the investable security and the thesis — e.g., a contract
   award to *"Lockheed Martin Rotary and Mission Systems"* resolves to `LMT`, its
   segment, its program, and (via supply-chain edges) the second-order beneficiaries
   most tools miss.
2. **Provenance by construction.** Every ingested record carries a source URL and
   timestamp, so every brief claim is citable. There is no uncited assertion.
3. **A published accuracy bar.** A built-in eval harness scores each brief for
   citation-faithfulness and flags unsupported claims before publish.
4. **"What changed" focus.** Change detection over the graph means each brief is
   signal — what's new since yesterday — not a re-summary of the same headlines.
5. **Free-data moat.** The sources that make HPI credible (USAspending, EDGAR, EIA,
   NRC, FRED, Congress.gov, BIS) are public and free. The moat and the low cost
   point the same way.

---

## How it's built

| Layer | Technology |
|-------|------------|
| Web | Next.js (Vercel) — marketing site, reader, Lemon Squeezy checkout |
| Mobile *(later)* | React Native + Expo, as a log-in-only "reader" app |
| Backend | FastAPI |
| Data / auth | Supabase (Postgres + pgvector) |
| Intelligence engine | source adapters → scheduler → entity-resolution graph → RAG synthesis → eval gate |
| LLM | OpenRouter (DeepSeek V4 Flash/Pro, Qwen3.7 Max) + Anthropic SDK (last-resort fallback) — ~$0.09/brief |
| Payments | Lemon Squeezy — Merchant of Record (web-first reader model) |

**Pipeline shape:** a per-source scheduler fetches each source at its own cadence →
adapters emit immutable, hashed, cited records → entity resolution writes provenanced
edges into a bitemporal graph → change-detection + graph-grounded RAG generate a
cached BLUF brief per desk → a citation/entailment gate verifies it before publish →
the brief renders to web cards and PDF.

Full design in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Monetization

Web-first subscriptions billed through Lemon Squeezy as Merchant of Record (reader-app
model — subscriptions are sold and managed on the web to avoid app-store commissions). Tiered: a free daily
brief (current day), a Pro tier ($19/mo or $179/yr) with archive, entity 360, PDF
export, and follows, and premium deep-dive reports in later cycles. Designed to run cheaply (~$80–230/mo infrastructure) and reach
break-even at a small number of subscribers.

---

## Status & scope

**Cycle 1 ships one vertical deep: the Defense desk, web-only.** Energy and
AI-Infrastructure desks, the mobile reader app, and second-order supply-chain
synthesis follow in a later cycle. This is an active, early-stage build.

Scope boundaries in [docs/SCOPE.md](docs/SCOPE.md).

---

## Engineering governance

This repository is built under **[Meridian](https://github.com/PCSchmidt/meridian)**,
an agent-harness framework that enforces a gate-by-gate workflow with schema-validated
memory and independent evaluation. HPI also serves as a Meridian **dogfooding
exercise**: its hybrid nature (a full-stack web app whose core is an ML/RAG eval
pipeline) exercises Meridian's composable gate DAG. Build progress is tracked through
`.meridian/gates.yaml`.

---

## Documentation

| Doc | Purpose |
|-----|---------|
| [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md) | Why HPI exists; the engine thesis, the moat, design principles, regulatory posture |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design: pipeline, entity graph, scheduler, adapters, brief generation |
| [docs/SCOPE.md](docs/SCOPE.md) | In/out of scope, build cycles, the three desks, success criteria |
| [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) | Source categories, free-vs-paid tiers, licensing posture |

---

## Disclaimer

Hard Power Intelligence produces **informational research, not investment advice**.
Nothing it generates is a recommendation to buy or sell any security. Always do your
own research.

---

## Author

**Paul Christopher Schmidt** — [@PCSchmidt](https://github.com/PCSchmidt)
