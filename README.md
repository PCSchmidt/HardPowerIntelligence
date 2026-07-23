# Hard Power Intelligence

**Markets intelligence on the AI, defense, and energy build-out.**

> **🌐 Live now at [hardpowerintel.com](https://hardpowerintel.com/)**
>
> The site is up and running, and today's briefings are **free to read right now** — no account required to see them. Paid subscriptions are on the way, but the checkout isn't wired to a payment processor yet, so for the moment everything on the site is open. If you're an investor, analyst, or just curious, go read a live brief and come back.

---

## The short version (start here)

Imagine hiring a sharp research analyst whose entire job is to read the boring-but-important stuff — thousands of pages of government contracts, corporate filings, regulatory notices, and industry news — every single day, across three industries: **artificial intelligence, defense, and energy.** Instead of handing you a pile of raw documents, this analyst hands you a single short briefing that leads with the point, tells you which companies each development actually affects, and shows you exactly where every fact came from so you can check the work yourself.

That analyst is what Hard Power Intelligence automates.

Most people who follow these markets don't have too little information — they have far too much of it, scattered across dozens of government websites and news feeds, written in dense bureaucratic language, and disconnected from what it means for the companies and stocks involved. A defense contract award, an energy regulator's licensing decision, a chipmaker's filing — each is public, but reading them all, connecting them, and figuring out what changed and why it matters is a full-time job. HPI does that work on a schedule and delivers the result as a clean briefing.

Three ideas make it trustworthy rather than just another news summarizer:

- **It leads with the bottom line.** Each briefing is written "BLUF" — *Bottom Line Up Front*, a style borrowed from military and intelligence reporting. You get the conclusion first, then the supporting detail, so you're not hunting for the point.
- **It shows its sources.** Every item links back to the original document — the actual contract, filing, or regulatory notice — so nothing has to be taken on faith. You can always click through and verify it yourself.
- **It labels how sure it is.** Every item is graded by confidence: a *confirmed* fact from a primary record looks different from *reported* news, which looks different from *HPI's own analysis* or *speculation*. You always know whether you're reading a hard fact or an interpretation.

The name is a play on three kinds of *power*: **hard power** (defense), **electrical power** (energy), and **compute power** (AI) — the three forces this product tracks, and increasingly the three forces that overlap. A single company can sit at the intersection of all three, and spotting those overlaps is where HPI aims to be most valuable.

HPI is a research and reporting tool, **not investment advice and not a stock-picker.** It tells you what happened and why it might matter; what you do with that is up to you.

---

## The detailed version

Hard Power Intelligence (HPI) turns scattered public data — SEC filings, federal
contract awards, energy and macro releases, regulatory actions, and news — into
**source-attributed, confidence-graded BLUF intelligence briefings** for investors tracking the
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
**Bottom-Line-Up-Front (BLUF)** brief where **every item shows its basis and
confidence** — from confirmed primary records to attributed reporting and
clearly-labeled HPI analysis. One shared brief per sector desk serves all
subscribers, so the marginal cost of another reader is near zero.

The product is positioned as **source-attributed research and reporting** — an
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
   timestamp, so every item can show its basis. Grounding is transparency the reader
   can check — not a filter that withholds important-but-not-airtight signal.
3. **A published accuracy bar.** A built-in eval harness flags fabricated specifics
   before publish and grades each item's confidence/attribution (confirmed →
   reported → HPI analysis → speculative), turning hallucination — the industry's
   weakness — into a visible trust signal.
4. **"What changed" focus.** Change detection over the graph means each brief is
   signal — what's new since yesterday — not a re-summary of the same headlines.
5. **Wide-net intake, free-data backbone.** HPI takes any on-thesis development with
   a linkable source; public primary records (USAspending, EDGAR, EIA, NRC, FRED,
   Congress.gov, BIS) are the free, credible *backbone*, not the only admissible
   source. The moat is judgment and the entity graph over a wide intake.

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
cached BLUF brief per desk → an eval gate checks it for fabrication and grades each
item's attribution before publish → the brief renders to web cards and PDF.

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

**Deployed to production 2026-06-12** — the full stack is live end-to-end: web reader
(Vercel) → API (Fly.io) → Supabase, with auth and a cited Defense brief at `/desk/defense`.
Gates 1–8 closed. This is an active, early-stage build.

**Since launch (2026-06-14):** the product is organized around the **Defense Tech ∩ AI ∩
Energy convergence** thesis — its north-star (`DECISIONS.md` D060). The engine moved off
fixtures onto live data and became genuinely multi-desk:

- **Production ingestion runner** (`scripts/run_ingest.py`, D057) — pulls fresh data through
  a retry/backoff fetcher with DB-level dedup, per-source cursors + accounting, a circuit
  breaker, and hot-window retention. The `daily-brief.yml` cron is **live** (06:00 UTC, ingest
  once → publish all three desks), made safe to run unattended by the reliability work below.
- **Layered analyst brief (2026-06-16, D071/D073)** — each item pairs the cited fact with a
  grounded `read` (why it's material) and `watch` (forward catalyst), plus a brief-level
  `convergence_read`, rendered as an "Analysis — HPI interpretation" drill-down (P3). The
  analysis is held to a grounding gate (regenerate-then-omit) so it adds interpretation without
  fabricating — depth that keeps the trust model. Reliability + freshness gates make daily
  publishing trustworthy: provable-claim publish floor (D070), regenerate-on-failure (D072),
  and a novelty/anti-rehash gate so tomorrow isn't a re-summary of today (D074).
- **Four live adapters** — **USAspending** (defense-tech awards, thematically scoped cross-agency
  not DoD-only, D059), **SEC EDGAR** (full-text search, the first cross-desk source — one adapter
  feeds all three desks, D061), **arXiv** (the technology-advancement leg, D066), and **NRC** (via
  the Federal Register API — the Energy desk's regulatory leg: nuclear/SMR licensing and HALEU
  fuel events, D095).
- **Convergence-aware, multi-desk briefs** — generation is desk-scoped across Defense / AI /
  Energy (D062); a record touching ≥2 desks is boosted as the convergence signal (D060). All
  three desks publish from live data with the layered analyst voice (BLUF → at-a-glance ledger →
  convergence → cited facts → grounded analysis → GDELT signal). A strategic-significance gate
  (D085) drops true-but-trivial items so a desk skips cleanly rather than publishing filler.
- **Entity-resolution graph (live, D091/D092)** — the moat (the "transmission layer"): a
  SEC-seeded reference entity set (~8k companies, de-duped by CIK) and a precision-first resolver
  held to an accuracy eval gate (precision 1.000 / recall 1.000 / zero false links on the golden
  set). Each brief item is resolved to the investable entities behind it and rendered as **entity
  chips** (ticker for public companies; a "private" chip for closely-held/venture firms, which are
  minted from authoritative ingest identifiers (UEI/CIK), not a curated list). Verified end-to-end
  on a live brief (every link correct, zero false positives). Chips click through to **Entity 360**
  pages (`/entity/[id]` — identifiers, the desks an entity spans, recent appearances), and an entity
  seen on ≥2 desks is flagged as a **cross-desk convergence** signal — the moat, live end-to-end.
- **Interactive Convergence Graph (live, D146–D153)** — the entity graph made visible at **`/graph`**:
  an interactive, on-brand force-directed map where companies recurring together across desks cluster,
  with gold **convergence nodes** (spanning ≥2 desks) and gradient edges that blend the two sectors they
  bridge. Built as: cross-desk co-appearance edges (`CONVERGES_WITH`), a name-gazetteer that lifts
  linking past the identifier-only ceiling, a filtered graph API, the interactive viz, edge-hover that
  surfaces the **cited stories behind each connection**, and a toggleable **federal-funding overlay**
  (`AWARDED` agency→company edges from USAspending — the first structured semantic layer). Behavior is
  instrumented so demo reactions are never mistaken for demand.

Remaining before public launch: Lemon Squeezy go-live (the checkout/webhook code is built;
needs account creds + variant IDs in Vercel/Fly — config, not engineering), a live-validation
pass on the AI/Energy desks plus dedicated sources for depth (EIA/NRC, interconnection queues,
more AI-infra), and the flagship cross-domain **convergence brief**. Auth config (Supabase Site
URL) is fixed. Tracked in `DEPLOYMENT_CONFIG.md` §6 and `CHANGELOG.md`.

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

## License

Source-available under the [PolyForm Noncommercial License 1.0.0](LICENSE). You're welcome
to read, study, fork, and build on this code for any **noncommercial** purpose. **Commercial
use requires a separate license** from the author — please get in touch. This is not an
OSI "open source" license; commercial rights are reserved.

---

## Author

**Paul Christopher Schmidt** — [@PCSchmidt](https://github.com/PCSchmidt)
