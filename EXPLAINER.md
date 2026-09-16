# Hard Power Intelligence — Engineering Explainer

*A recruiter/interviewer-facing summary of a solo-built, production AI system.*
*Built by Chris Schmidt, ~7 weeks part-time (June–July 2026), while working full-time as an ML Engineer.*

---

## The pitch

Hard Power Intelligence is a production system that reads public government and market
data every day — SEC filings, federal contract awards, nuclear licensing records, arXiv
papers, news — resolves every company mentioned into a canonical, investable entity, and
uses an LLM pipeline to write a short daily intelligence brief per sector, with every
sentence traced back to a cited source and labeled by confidence. It's live today at
hardpowerintel.com, publishing free daily briefs across three "desks" (Defense, AI
Infrastructure, Energy). It is pre-revenue and pre-traction: the product works and is
running unattended in production; it has not yet been marketed to real subscribers.

What makes it interesting from an engineering standpoint isn't "I called an LLM API" —
it's that most of the hard problems are the ones any production LLM system runs into and
this one has documented, working answers for: how do you stop an LLM from making things
up, how do you keep the bill from exploding, what happens when your LLM provider goes
down mid-pipeline, and how do you turn "acme corp" mentioned in a press release into the
same row as "Acme Corporation" mentioned in a 10-K.

---

## System architecture

```text
GitHub Actions (cron, 06:00 UTC daily)
  │
  ├─ Ingestion: adapters for USAspending, SEC EDGAR, arXiv, NRC, GDELT, RSS/Atom, SAM.gov
  │     fetch (network, impure) → parse (pure) → raw_records (hashed, immutable)
  │     → normalized_records (entity mentions, text chunks, pgvector embeddings)
  │
  ├─ Entity resolution: crosswalk (SEC ticker/CIK, OpenFIGI, GLEIF LEI, SAM UEI)
  │     → fuzzy (pg_trgm) + semantic (pgvector) candidates → LLM disambiguation
  │     → entities / entity_edges knowledge graph
  │
  ├─ Brief generation (Defense / AI / Energy desks, run in parallel):
  │     materiality scoring (filter before spending on LLM calls)
  │     → graph-grounded RAG retrieval (structured facts + vector passages, each citation-indexed)
  │     → LLM synthesis (JSON, [CITE:N] markers)
  │     → citation-faithfulness eval (LLM-as-judge, entailment per sentence)
  │     → confidence labeling → persist
  │
  ├─ Convergence graph rebuild: cross-desk co-appearance + funding edges
  │
  └─ Health check: inspects its own run telemetry, pages via Resend on silent failure

Next.js (Vercel) ──▶ FastAPI "hpi-api" (Fly.io) ──▶ Supabase (Postgres + pgvector, Auth, RLS)
                                                  ↕
                                        Lemon Squeezy (subscriptions, built not yet live)
```

**Stack:** Python 3.12 / FastAPI / asyncpg / Pydantic v2 (backend + engine), Next.js 16 /
React 19 / Tailwind v4 / TanStack Query (frontend), Supabase (Postgres + pgvector + Auth +
RLS), LiteLLM routing OpenRouter (DeepSeek, Qwen) with a Fireworks cross-provider fallback,
OpenAI embeddings, Vercel + Fly.io + GitHub Actions + Cloudflare + Sentry + Resend +
PostHog for infra/observability. `uv` monorepo workspace for the Python packages.

---

## Five things worth talking about in an interview

### 1. A RAG pipeline with a hard anti-hallucination gate

Every sentence in a generated brief carries a `[CITE:N]` marker that maps deterministically
to a specific source record. Retrieval is *graph-grounded*: hard facts (amounts, dates,
tickers) come straight from the entity graph — a non-hallucinable spine — and only
surrounding narrative context comes from vector search over source text. A second LLM
call, acting as judge, checks each claim for entailment against its cited source before
publish; claims that fail are dropped from the brief rather than allowed through. This
started as a hard publish-blocking threshold and was later deliberately changed to a
confidence *label* instead of a gate, after concluding that suppressing true-but-thinly-cited
signal was worse than showing it honestly labeled — a real reversal, not a plan followed
blindly.

### 2. Root-caused and fixed a real multi-day production outage

On 2026-07-25 the site went dark because a single LLM provider account ran out of
credits — every brief silently failed to generate. Rather than just topping up the
account, the response was to build structural resilience: a cross-provider fallback
(OpenRouter → a separate-billing-account Fireworks endpoint) so no single vendor's
billing state can dark the product. The next day it broke again for an *unrelated*
reason (the health check itself had a blind spot — it only checked account credits, not
per-key rate limits), which led to a second round of fixes: a two-phase fallback, a
credit-refill wait state, and a health probe that reads both credits and key limits. Two
days later, a hand-rolled fallback-chain walker replaced LiteLLM's built-in `fallbacks=`
because it was silently collapsing errors and skipping the last-resort path entirely —
diagnosed by testing the failure path directly, not assumed to work. This is documented,
end-to-end, across five real commits (D155–D159).

### 3. An entity-resolution knowledge graph with a measured accuracy target

Turning "the mentioned company" into "the correct row in a database" is a four-tier
cascade: deterministic crosswalk lookup (SEC ticker/CIK, OpenFIGI, GLEIF LEI, SAM UEI) →
fuzzy string + semantic vector candidate generation → cheap-LLM disambiguation → an
auto-dismiss tier for genuine no-matches. It's held to a golden-set precision/recall
eval, seeded from ~8,000 SEC-registered companies. The graph is then used for more than
lookup: a `CONVERGES_WITH` edge type tracks which companies co-appear across desks
(recency-decayed, cross-desk-boosted), and an `AWARDED` edge type tracks government
funding relationships — surfaced in an interactive graph view built with a hand-rolled
force-directed layout algorithm (no d3 dependency).

### 4. Cost-engineered LLM orchestration

Rather than one model doing everything, five distinct pipeline roles (extraction,
disambiguation, synthesis, eval, fallback) are each pinned to a specific model chosen for
that role's cost/capability tradeoff — bringing brief cost down roughly 4x versus using a
single frontier model everywhere. Swapping a model into any role requires it to beat the
current baseline on the faithfulness eval across the last 30 real briefs before
promotion — a formal regression gate for a nondeterministic component, not "seems fine."

### 5. Full-stack delivery with a real, fixed security finding

Auth, JWT verification (including fixing an HS256/ES256 mismatch), Row-Level Security,
and a Lemon-Squeezy-based payments integration (chosen over Stripe specifically to
offload global VAT/tax compliance as a solo operator) were all built and deployed solo
(payments are live in code, not yet activated for billing).
A structured security audit against the OWASP Top 10 (plus AI-specific risks) found a
real vulnerability pre-launch — the paywall was bypassable via direct PostgREST access to
Supabase, sidestepping the API entirely — which was fixed with an RLS lockdown migration
and verified in production.

---

## Honest scope and boundaries

Deliberately **not** built, as a standing decision rather than an oversight: personalized
per-user brief generation (kept off to keep marginal reader cost near zero, and to stay
in a "publisher," not "advisor," regulatory posture), buy/sell recommendations, portfolio
management, or brokerage integration. The product explicitly stays in the lane of
research-with-citations, never advice — a boundary that was drawn deliberately and
repeatedly reaffirmed rather than discovered after the fact.

## What this is, honestly

- **Built by:** one engineer (me), solo, in close collaboration with LLM coding tools
  (Claude Code) — the tool helped write code; the architecture decisions, tradeoffs, and
  incident diagnoses documented above were mine.
- **Timeline:** ~7 weeks of part-time work (June–July 2026) alongside a full-time job.
- **Status today:** live in production, publishing daily, same scope as documented above.
  Payments are built and wired to Lemon Squeezy but intentionally not turned on yet.
- **Traction:** pre-revenue, pre-subscriber. This is a demonstrated engineering system,
  not (yet) a validated business — and I'd say that plainly in an interview rather than
  imply otherwise.
