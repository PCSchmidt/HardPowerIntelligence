# Architectural Decisions — Hard Power Intelligence

Key decisions made before the build started, and why. When a decision is revisited,
update this file and note the date.

---

## D001 — Defense desk first, not all three simultaneously

**Decision:** Launch with the Defense desk only (Cycle 1). Energy and AI-Infrastructure
desks follow in Cycle 2 after the format and engine are validated.

**Why:** The entity-resolution graph, adapter framework, brief generator, and citation
eval harness are the same machinery for all three desks. Getting them right on one desk
before scaling to three avoids building three broken pipelines in parallel. The Defense
desk is chosen first because it has the richest free government data (USAspending,
SAM.gov, DoD contracts, Congress.gov, DSCA, BIS) and the most clearly identifiable
buyer. "One vertical deep before three shallow" is Philosophy principle 6.

---

## D002 — Web-first; mobile reader app in Cycle 2

**Decision:** Cycle 1 is web-only (Next.js on Vercel). React Native + Expo reader app
and app-store submissions are Cycle 2.

**Why:** The intelligence engine (the product's core value) is the same regardless of
the reader surface. Validating it on web first — with real subscribers, real briefs,
and real citation scores — before porting to mobile avoids building a reader app for a
pipeline that hasn't been proven. Reader-app model (subscriptions managed on web) also
avoids Apple/Google commission on subscription revenue from day one.

---

## D003 — Shared output, not per-user generation

**Decision:** One brief per desk per cadence, shared to all subscribers. Personalization
is filtering and reordering the shared brief by a user's followed entities, never
per-user regeneration.

**Why:** Per-user generation would multiply LLM cost by subscriber count, making the
cost model unworkable at any meaningful scale. Shared output means the marginal cost of
an additional reader is near zero. It also maintains the publication posture
(non-personalized research) that keeps HPI in the publishers' exemption lane.

---

## D004 — APScheduler + Postgres job queue for MVP; Celery deferred

**Decision:** Use APScheduler with a Postgres job queue (`FOR UPDATE SKIP LOCKED`) for
the source scheduler. Do not introduce Redis or Celery until throughput demands it.

**Why:** Redis + Celery adds operational complexity (another service, another failure
mode, another cost line). A Postgres-backed queue is sufficient at MVP scale, already
has the database for job state, and Supabase `pg_cron` can enqueue due jobs. Upgrade
path to Celery is clear if queue depth or throughput becomes a bottleneck.

---

## D005 — Supabase for database, auth, and vectors

**Decision:** Use Supabase (managed Postgres + pgvector) for the graph, ingestion
tables, briefs, user accounts, and vector search. Row-level security for all user data.

**Why:** Supabase bundles Postgres, auth, row-level security, pgvector, and a REST/
realtime API in one managed service with a generous free tier. Running a separate auth
service, a separate vector DB, and a separate Postgres instance at MVP would multiply
complexity without adding capability. pgvector handles semantic search for entity
disambiguation at the scale of this dataset; a dedicated graph DB (Apache AGE, Neo4j)
is deferred until traversal scale demands it.

---

## D006 — LLM waterfall: cheap models for extraction, strong model for synthesis

**Decision:** Use cheap models (e.g., Claude Haiku) for entity extraction, clustering,
and candidate selection. Use the strong model (e.g., Claude Sonnet/Opus) only for
final brief synthesis.

**Why:** LLM cost is the dominant variable in the run cost. The strong model is only
needed at the final synthesis step where prose quality matters. Extraction and
clustering are pattern-matching tasks that cheap models handle reliably. Waterfall
reduces synthesis cost by 5–10x versus using the strong model throughout.

---

## D007 — Free-first data stack; paid data deferred until revenue

**Decision:** Build entirely on Tier-0 free public sources for Cycle 1, plus one cheap
data vendor (FMP ~$19/mo). No Bloomberg, AlphaSense, FactSet, or real-time licensed
feeds until subscribers fund them.

**Why:** The sources that make HPI credible for these verticals (USAspending, EDGAR,
EIA, NRC, Congress.gov, BIS) are public, free, and freely redistributable. The moat
(provenance over free strategic data) and the cost advantage point the same direction.
Expensive licensed feeds add cost and legal complexity without proportionally adding
credibility for the thesis HPI is built around.

---

## D008 — Provenance at ingestion, not as a UI feature

**Decision:** Every `RawRecord` carries `url + fetched_at + content_hash` at the
moment of ingestion. Citations are guaranteed downstream because they are guaranteed
at the source.

**Why:** Trying to add citations as a post-processing step (asking the model to
attribute its output) is unreliable. Building provenance into the record schema means
citations are structural — they cannot be lost or hallucinated away by a synthesis step.
This is what makes the "no uncited claim" guarantee checkable by an automated eval.

---

## D009 — FastAPI as the API layer; Next.js frontend separate

**Decision:** FastAPI (Python) for the API backend. Next.js (App Router) for the
frontend. They are separate services, not a monolith or a Next.js API-routes backend.

**Why:** The intelligence engine is Python (adapters, entity resolution, brief
generation, eval harness). Keeping the API in Python avoids a cross-language RPC
boundary between the engine and the API layer. Next.js is the best choice for the
web reader (SEO, streaming, Vercel deployment) but is not the right choice for a
data-pipeline backend. Separation lets each scale independently.

---

## D010 — Meridian gate governance from day one

**Decision:** Install Meridian (agent-harness framework) before writing any application
code. Gate progression enforces design-before-build: CONTRACT.md, SPEC.md, DECISIONS.md
before code; API_SPEC.md and DATABASE_SCHEMA.md before backend; FRONTEND_SPEC.md
before UI; citation eval passing before web reader; tests passing before deploy.

**Why:** HPI is a complex multi-layer system (scheduler + adapters + entity graph + RAG
+ eval + web + auth + payments). The "last 10% collapse" — where everything seems done
but the pieces don't integrate — is the failure mode Meridian is designed to prevent.
Gate enforcement also tracks calibration (predicted vs. actual hours) and forces
independent evaluation of each phase before proceeding, surfacing integration failures
early rather than at deploy time.
