# Architecture

System design for Hard Power Intelligence: the pipeline that turns disparate public
sources into cited BLUF briefings, and the components that make it reliable, fresh,
and cheap to run.

---

## 1. Pipeline overview

```
 SCHEDULER → [ ADAPTER.fetch(cursor) ] → raw_records (immutable, URL + ts + hash)
                                              │
                                   [ ADAPTER.parse() ] → normalized_records + entity_mentions
                                              │
                                   ENTITY RESOLUTION → ENTITY GRAPH (cited, bitemporal edges)
                                              │
   last_brief ──► [ CHANGE DETECTION ] ──► candidate events (ranked by materiality)
                                              │
                          [ GRAPH-GROUNDED RAG SYNTHESIS (model waterfall) ]
                                              │
                          [ CITATION BINDING + EVAL GATE ] → Brief (JSON)
                                              │
                                   web cards + PDF  (shared output, cached)
```

Ingestion (scheduler + adapters + resolution) and synthesis (brief generation) are
**decoupled**: ingestion continuously fills the graph; brief generation reads the
freshest graph state on its own cadence and diffs against the last brief.

---

## 2. Stack

| Layer | Technology | Role |
|-------|------------|------|
| Web | Next.js (Vercel) | Marketing, reader UI, Lemon Squeezy checkout, SEO |
| Mobile *(later)* | React Native + Expo | Log-in-only "reader" app |
| API | FastAPI | Brief API, auth, Lemon Squeezy webhooks |
| Data / auth / cache | Supabase (Postgres + pgvector) | Graph, records, briefs, users, vectors |
| LLM | OpenRouter (DeepSeek V4 Flash/Pro, Qwen3.7 Max) + Anthropic SDK last-resort (D006) | Cost-controlled waterfall |
| Payments | Lemon Squeezy (MoR) | Web-first subscriptions (reader model); global tax handled (D050) |
| Infra | Cloudflare, Sentry, PostHog, Resend | DNS/WAF, errors, analytics, email |

---

## 3. The entity-resolution graph (the transmission layer)

The core asset: a graph that collapses every source's view of a company into one
canonical entity and remembers how things connect.

**Node types:** company, security, segment/business-unit, program, person,
institution, gov-agency, sector/theme, product/technology, facility, geography.

**Edge types (carry properties + provenance):** `HAS_SECURITY`, `FILES_AS`,
`REGISTERED_AS`, `PARENT_OF`, `RUNS_PROGRAM`, `AWARDED`, `SUPPLIES`, `COMPETES_WITH`,
`INSIDER_OF`, `TRANSACTED`, `HOLDS`, `MEMBER_OF`, `PRODUCES`, `EXPOSED_TO`, `OPERATES`.
The highest-value edges are `SUPPLIES` and `PARENT_OF` — they enable second-order
traversal (AI capex → suppliers → utilities).

**Resolution pipeline (mention → entity_id):**
1. **Deterministic** crosswalk lookup (free identifier registries — see below). Most
   of the high-value defense/energy data is structured and resolves here, O(1).
2. **Normalize** name (uppercase, strip Inc/Corp/LLC, expand abbreviations).
3. **Candidate generation** via `pg_trgm` fuzzy + `pgvector` semantic match.
4. **Score**: high → auto-link; medium → cheap-LLM disambiguation with candidates +
   context; low → human review queue.
5. **Cache** the mapping so future mentions are deterministic.

**Free crosswalk backbone:** SEC `company_tickers.json` (ticker↔CIK), OpenFIGI
(ticker/CUSIP↔FIGI), GLEIF LEI (legal-entity parent/child), SAM.gov/USAspending
recipient hierarchy (UEI↔parent).

**Bitemporal** (`valid_from`/`valid_to`): companies rename and reorganize
(Raytheon→RTX, L3+Harris→L3Harris). Two time axes — *valid time* (true in the world)
and *transaction time* (when learned) — let briefs answer "as of Q2 2024, who held
this," and never silently overwrite history.

**Storage:** modeled in Postgres (`entities`, `entity_identifiers`, `entity_aliases`,
`entity_edges`, `resolution_queue`). Apache AGE is an optional in-Supabase upgrade;
a dedicated graph DB is deferred until traversal scale demands it.

---

## 4. The source scheduler

Each source is polled at its own **half-life**, driven by a `source_registry` table —
not a single global cron.

- **Interval/cron** for unscheduled sources (news, filings sweep).
- **Calendar-pinned** for known release times (CPI 8:30am on its date, FOMC, earnings,
  the 13F deadline) — fetch shortly after release instead of blind polling.
- **Adaptive cadence** — raise frequency around catalysts, back off when quiet.
- **Incremental fetch** via per-source watermarks/cursors (fetch only deltas).
- **Reliability** — token-bucket rate limits, exponential backoff, a circuit breaker
  that isolates a dead source, and a budget guard that pauses paid sources at a cap.

Cadence ranges from continuous (news 15–30 min, 8-K sweep) through daily (EDGAR sweep,
USAspending awards, EIA, FRED) to quarterly (13F). The same calendar that schedules
fetches also powers the user-facing **catalyst calendar**.

**Implementation (solo-dev pragmatic):** `hpi-worker` runs procrastinate with
`@app.periodic` decorators for scheduling — no `pg_cron` required (D004/D025).
Upgrade to Redis/Celery only if throughput demands it.

---

## 5. The adapter contract

Every source — REST API, RSS, HTML scrape, bulk file, calendar — implements one
uniform contract so the scheduler, dedup, provenance, and resolution layers treat them
identically.

- `fetch(cursor)` is **impure** (network); `parse()` is **pure** (bytes → records),
  so parsing is unit-testable against recorded **golden fixtures**.
- Every `RawRecord` carries `url + fetched_at + content_hash` — **provenance by
  construction**, which is why downstream citations are real.
- Each adapter declares a **`license_class`** (`public_domain | licensed |
  scrape_gray`) that routes the legal posture automatically: gov data may be stored
  and redistributed; licensed data is synthesized + cited, never republished raw;
  paywalled press is link + short-quote only. The renderer reads this flag to decide
  how much text it may show.
- **Dedup** by `(source_id, native_id)` + `content_hash`; re-running an adapter is
  always safe.

Transport base classes (`RestApiAdapter`, `RssAdapter`, `HtmlScraperAdapter`,
`BulkFileAdapter`, `CalendarAdapter`) handle auth/pagination/backoff/robots.txt, so a
concrete adapter is small. Adding source #40 = one registry row + one adapter, no
rewrite.

---

## 6. Brief generation (RAG + change detection)

Runs on the brief cadence, decoupled from ingestion, producing **one shared, cached,
verified brief per desk**.

1. **Change detection** — diff the graph since the last brief (new edges, new records,
   numeric series moves past threshold). Each candidate scored by **materiality**
   (source authority + novelty + magnitude + entity importance + corroboration).
   Low-materiality noise is dropped *before* any LLM spend.
2. **Graph-grounded hybrid retrieval** — structured **facts** from the graph (the
   non-hallucinable spine: amounts, dates, resolved tickers, 1–2 hop neighbors) plus
   unstructured **passages** from text (color/quotes via pgvector), each carrying a
   citation id.
3. **Waterfall synthesis** — cheap models cluster/select; the strong model writes
   final prose constrained to cited facts/passages.
4. **Citation binding + eval gate** — every claim carries a citation id; a verifier
   (entailment check for prose, exact-match for numbers) confirms each claim against
   its source before publish. A brief below the faithfulness threshold does not ship.
   This is the eval harness, run on every brief; its score is a published product
   metric.
5. **Output + render** — one `Brief` JSON renders to web cards and PDF; `citations[]`
   becomes the source drawer; `license_class` decides full-quote vs link-only.
   Personalization = filtering/reordering by a user's follows, never regeneration.

---

## 7. Data model (high level)

| Group | Tables |
|-------|--------|
| Graph | `entities`, `entity_identifiers`, `entity_aliases`, `entity_edges`, `resolution_queue` |
| Ingestion | `source_registry`, `ingestion_runs`, `raw_records`, `normalized_records` |
| Product | `briefs`, `brief_items`, `citations`, `calendar_events` |
| Accounts | `users`, `subscriptions`, `follows` (with row-level security) |
| Vectors | `pgvector` columns on aliases + text chunks |

---

## 8. Cost model

- **Data cost at MVP ≈ $0** (free public Tier-0 sources) + ~$19/mo for one market-data
  vendor (FMP).
- **LLM cost is low by design.** The waterfall routes through OpenRouter to
  cost-optimized models; Claude Sonnet is only the last-resort fallback.

| Role | Model | Est. tokens/brief | Est. cost/brief |
|------|-------|-------------------|-----------------|
| Extraction | DeepSeek V4 Flash ($0.28/M out) | 30K in / 5K out | ~$0.005 |
| Disambiguation | DeepSeek V4 Flash | 10K in / 2K out | ~$0.002 |
| Synthesis | DeepSeek V4 Pro ($3.48/M out) | 25K in / 4K out | ~$0.057 |
| Eval gate | Qwen3.7 Max ($3.75/M out) | 15K in / 2K out | ~$0.026 |
| **Total** | | | **~$0.09/brief** |

  One brief serves all subscribers (shared output). At 365 briefs/year per desk:
  ~$33/year for one desk, ~$100/year at full three-desk Cycle 2 scale. All LLM spend
  is capped by a budget guard that pauses synthesis if the daily threshold is exceeded.

- **Infrastructure ~$80–230/mo** (Vercel, Supabase Pro, Fly.io ×2 services, Resend,
  Sentry).
- Break-even at a small number of subscribers; every reader past that is margin.

See [DATA_SOURCES.md](DATA_SOURCES.md) for the source-by-source breakdown.
See [DECISIONS.md](../DECISIONS.md#d006) (D006) for model selection rationale and upgrade process.
