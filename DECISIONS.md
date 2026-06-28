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

## D004 — Postgres job queue with procrastinate; Celery deferred *(updated 2026-06-05)*

**Decision:** Use **`procrastinate`** (a Python async task queue backed by Postgres) for
the source scheduler. Procrastinate's `@app.periodic` decorator registers each source's
fetch schedule directly in Python code; the `hpi-worker` process owns the schedule
lifecycle entirely. `pg_cron` is **not required** — procrastinate stores periodic task
state in `procrastinate_periodic_defers` and fires jobs without any Postgres extension.
APScheduler is not used. Do not introduce Redis or Celery until throughput demands it.

*(Updated 2026-06-05: dropped pg_cron dependency. pg_cron requires Supabase Pro and is
not available on the free tier. Procrastinate's native PeriodicTask achieves the same
result with no infrastructure dependency. If Supabase Pro is adopted for other reasons,
pg_cron can coexist as a secondary trigger but adds no functional value for Cycle 1.)*

**Why:** APScheduler running inside a process stores its schedule in memory. If the
process restarts, in-flight jobs are lost and the schedule resets. For a paid
subscription product that promises a daily brief, silent ingestion failures are
unacceptable. A Postgres-backed queue is durable — jobs survive worker restarts because
they exist in the database, not in RAM. Procrastinate's `@app.periodic` handles the
schedule from the worker process; the jobs table is the audit log. `procrastinate` provides this
pattern out of the box with async support, retry logic, and job monitoring without
adding a second infrastructure dependency.

Upgrade trigger for Celery + Redis: queue depth consistently exceeding Postgres throughput
limits, or need for distributed task routing across heterogeneous worker pools. Not
anticipated before Cycle 3.

---

## D005 — Supabase for database, auth, and vectors *(updated 2026-06-05)*

**Decision:** Use Supabase (managed Postgres + pgvector) for the entity graph, ingestion
tables, briefs, user accounts, and vector search. Row-level security for all user data.
Large raw payloads (EDGAR filings, bulk downloads) are stored in **Supabase Storage**
(S3-compatible object storage) with a URL pointer in the `raw_records` table; small
structured payloads (<50KB) may be stored inline.

**Why:** Supabase bundles Postgres, auth, row-level security, pgvector, and a
REST/realtime API in one managed service with a generous free tier. Separate services
for auth, vectors, and storage would multiply complexity without adding capability.

**Raw payload routing:** EDGAR 10-K filings run 1–5MB each. Storing large payloads
inline in Postgres would exhaust Supabase's free-tier storage limit within months and
degrade query performance. Supabase Storage is the correct landing zone for large binary
payloads; the `raw_records.payload_url` column holds the pointer.

**Graph traversal ceiling:** Supabase's managed Postgres does not support Apache AGE
(which requires a custom-compiled Postgres build). The relational graph (entities +
typed edges + recursive CTEs) handles 1–4 hop traversals comfortably through Cycle 2.
The migration trigger for evaluating a dedicated graph layer is: all three desks live
+ supply-chain synthesis active + measurable query latency on 3+ hop traversals at
production load. At that point, the preferred option is a **hybrid**: Supabase retains
accounts, ingestion, and briefs; a Neo4j Aura instance handles deep graph traversal only.
The schema abstraction (entities + typed edges) is graph-portable — migration is a data
copy and query rewrite, not a redesign.

---

## D006 — LLM waterfall: OpenRouter + DeepSeek V4 + Qwen3.7, configuration-driven *(updated 2026-06-05)*

**Decision:** Use a model waterfall with five independently configurable roles, all
accessed via **LiteLLM + OpenRouter** except the last-resort fallback which calls the
Anthropic SDK directly. Model IDs are pinned in environment variables, never hardcoded.

**Waterfall configuration:**

| Role | Model | OpenRouter ID | Input/1M | Output/1M |
|------|-------|--------------|----------|-----------|
| Extraction | DeepSeek V4 Flash | `openrouter/deepseek/deepseek-v4-flash` | $0.14 | $0.28 |
| Disambiguation | DeepSeek V4 Flash | `openrouter/deepseek/deepseek-v4-flash` | $0.14 | $0.28 |
| Synthesis | DeepSeek V4 Pro | `openrouter/deepseek/deepseek-v4-pro` | $1.74 | $3.48 |
| Eval | Qwen3.7 Max | `openrouter/qwen/qwen3.7-max` | $1.25 | $3.75 |
| Synthesis fallback | Qwen3.7 Max | `openrouter/qwen/qwen3.7-max` | $1.25 | $3.75 |
| Last-resort fallback | Claude Sonnet 4.6 | direct Anthropic SDK | ~$3.00 | ~$15.00 |

**Why — model assignments:**
- *Extraction/disambiguation (V4 Flash):* Pattern-matching tasks cheap models handle
  reliably. $0.28/M output is ~50x cheaper than Sonnet for steps that do not require
  strong reasoning.
- *Synthesis (V4 Pro):* DeepSeek V4 Pro (1.6T MoE, 49B active, 1M context, 384K max
  output) handles constrained factual generation at high capability and low cost
  ($3.48/M vs $15/M output). The 384K max output ceiling matters: a detailed multi-story
  Defense brief with full citations must not hit truncation mid-generation.
- *Eval (Qwen3.7 Max):* The citation entailment check is a structured reasoning task —
  Qwen3.7 Max's design focus (agentic, reasoning, structured output, 1M context). 65K
  max output is sufficient for structured JSON verdicts. Benchmarks show Qwen3.7 Max
  competitive with or above Sonnet 4.6 on intelligence and reasoning at $3.75/M vs
  $15/M output.
- *Synthesis fallback (Qwen3.7 Max):* If DeepSeek V4 Pro is unavailable, Qwen3.7 Max
  is the fallback synthesis model. Its 65K output limit is a constraint for very long
  briefs; monitor and adjust if synthesis regularly approaches that ceiling.
- *Last-resort fallback (Claude Sonnet, direct Anthropic SDK):* Present not because
  Sonnet is preferred, but because it is on a different infrastructure path. If
  OpenRouter goes down, all OpenRouter-routed models fail simultaneously. A direct
  Anthropic SDK call bypasses that. It is insurance, not a preference.

**Estimated per-brief cost:** ~$0.09 (vs ~$0.40 all-Sonnet).
Three desks × 365 days ≈ $100/year vs $440/year at full Cycle 2 scale.

**Why — LiteLLM + OpenRouter:** LiteLLM normalizes the API across providers; OpenRouter
provides a single API key, load balancing, and provider-level redundancy for all
non-Anthropic models. No pipeline stage imports provider SDKs directly except the
Anthropic SDK last-resort path. Model swaps are environment variable changes, not code
changes. LiteLLM's built-in token and cost tracking feeds the budget guard directly.

**Why — model pinning:** The citation-faithfulness eval harness is the product's
credibility guarantee. If the eval model changes mid-run, scores drift and you cannot
distinguish quality regression from model change. Pin all roles to specific versioned
model IDs. Upgrades are deliberate: run the eval harness against the last 30 published
briefs with the candidate model; promote only if faithfulness score meets or exceeds
baseline; record the change here with date and reason.

**Availability fallback sequence (synthesis):**
1. DeepSeek V4 Pro via OpenRouter — retry 3× with exponential backoff
2. Qwen3.7 Max via OpenRouter
3. Claude Sonnet 4.6 via direct Anthropic SDK
4. If all three fail: trigger D013 (previous brief + staleness indicator + alert)

**Availability fallback sequence (eval):**
1. Qwen3.7 Max via OpenRouter — retry 3×
2. Claude Sonnet 4.6 via direct Anthropic SDK
3. If both fail: hold brief in `pending`; retry eval on next cycle

**Data routing note:** All synthesis and eval prompts contain public-domain data
(USAspending, EDGAR, DoD contracts). Routing through DeepSeek and Qwen infrastructure
is acceptable; all source data is publicly available.

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

## D009 — FastAPI on Fly.io, deployed as two services *(updated 2026-06-05)*

**Decision:** FastAPI (Python) for the API backend. Next.js (App Router) for the
frontend. They are separate services. The FastAPI backend is deployed to **Fly.io** as
**two distinct services**: `hpi-api` (the HTTP server handling brief requests, auth
validation, and Stripe webhooks) and `hpi-worker` (the long-running scheduler and
ingestion worker). Next.js is deployed to Vercel.

**Why — FastAPI:** The intelligence engine is Python. Keeping the API in Python avoids
a cross-language boundary between the engine and the API layer. Next.js is the right
choice for the web reader (SEO, streaming, Vercel) but not for a data-pipeline backend.

**Why — Fly.io over Railway:** The `hpi-worker` process must be persistent and
always-on — APScheduler/procrastinate runs continuously, and a sleeping worker stops
ingestion silently. Railway's lower tiers sleep idle services; Fly.io is designed for
persistent processes and does not sleep. Fly.io also provides better granularity on
machine sizing (~$2–5/mo for a shared-cpu-1x instance at MVP).

**Why — two services:** Separating `hpi-api` and `hpi-worker` means the reader-facing
API stays up if the worker crashes, and the worker can be restarted independently
without dropping in-flight HTTP requests. It also sets up the natural scaling path:
multiple worker instances can run safely against the same Postgres job queue via
`FOR UPDATE SKIP LOCKED`. Next.js API routes are used only for Stripe webhook
callbacks and auth redirects where required by those SDKs; all data fetching routes
through FastAPI.

**Rate limiting:** Cloudflare WAF rules handle edge-level throttling (100 requests/minute
per IP on `/v1/*`; already in the stack, zero additional cost). `slowapi` FastAPI
middleware enforces per-user limits on expensive endpoints: entity search (30/min),
entity 360 (20/min), PDF export (5/hour). No Redis required at MVP — `slowapi` uses
in-memory counters. Upgrade to Redis-backed limiting only if multiple `hpi-api`
instances run concurrently.

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

---

## D011 — Frontend-to-API boundary: FastAPI-first

**Decision:** Next.js never calls Supabase directly for application data. All data
fetching — briefs, entity data, subscription status, follows — routes through FastAPI
endpoints. Supabase is accessed server-side only (from FastAPI). The Supabase JS client
is used in Next.js only for authentication (session management, token refresh). Row-level
security remains enabled as defense-in-depth, but FastAPI is the primary authorization
layer.

**Why:** The Supabase-first alternative (Next.js using supabase-js for read operations
directly) splits business logic: some access control lives in RLS policies, some in
FastAPI middleware, and the split is invisible to the reader. When the Cycle 2 mobile
app is added, it calls the same FastAPI endpoints the web calls — there is one API
contract, not two. FastAPI is also where subscription tier is checked, budget guards
run, and brief access is gated — all of these belong in one place. The performance
cost of routing through FastAPI instead of querying Supabase directly is negligible for
this read volume.

---

## D012 — Subscription gating: FastAPI gates data, Next.js gates UX *(payment processor superseded by D050 — Lemon Squeezy; the dual-layer gating principle still holds)*

**Decision:** Subscription status is the source of truth in Supabase's `subscriptions`
table, updated exclusively by Stripe webhooks arriving at a FastAPI endpoint. FastAPI
validates the Supabase JWT on every request, resolves subscription tier, and gates
data access (returning 403 for Pro-only content to free-tier users). Next.js middleware
checks the session and handles UX routing (redirecting unauthenticated users to login,
unauthenticated users to the subscribe page) — but never trusts its own session as the
final authorization check. Both layers run; they serve different purposes.

**Why — Stripe webhooks via FastAPI:** Stripe sends events (subscription created,
payment failed, subscription cancelled) as HTTP POST requests. Handling these in
FastAPI keeps the subscription state update logic co-located with the rest of the
business logic, testable with standard Python tooling, and independent of Supabase
Edge Functions (which add a separate deployment target). FastAPI verifies the Stripe
webhook signature, updates `subscriptions`, and the change is immediately reflected in
subsequent API calls.

**Why — dual-layer gating:** Next.js middleware gates the UI route (so a free user
never sees the Pro page at all), while FastAPI gates the data (so even if someone
bypasses the UI, the API returns nothing). Defense in depth. The session claim (from
Supabase Auth JWT custom claims) can carry the subscription tier for fast UI routing
without an extra API call, but the FastAPI check is authoritative.

---

## D013 — Brief fallback when the eval gate fails or generation fails

**Decision:** When a brief fails the citation-faithfulness eval gate, or when brief
generation fails (LLM unavailable, synthesis error), subscribers are shown the **most
recently published passing brief** with a visible staleness indicator ("Last updated
X hours ago — next brief pending"). The failed/in-progress brief is held in a
`pending` state. A Sentry alert fires immediately. The `briefs` table tracks
`published_at`, `status` (`published | pending | failed`), and `faithfulness_score`
to support this.

**Why:** A paid subscriber must always see something — a "brief unavailable" blank
screen is a support ticket and a cancellation risk. The previous brief is still
accurate (it passed its own eval gate); its information is simply not the most current.
Showing it with a clear timestamp is honest and functional. Silently publishing a
failed brief is not an option — that is the product's core guarantee. The staleness
indicator preserves trust; blanking the page destroys it.

**Implication for schema design:** The `briefs` table must support multiple rows per
desk (one per day), with a `status` column and a query pattern for "latest published
brief for this desk." This is a Gate 2 (DATABASE_SCHEMA.md) requirement.

---

## D014 — Brief generation window: 5:30am ET daily *(updated 2026-06-05)*

**Decision:** The daily brief generation job runs at **5:30am ET**. The data-readiness
window closes at **5:00am ET** — sources scheduled to run overnight must complete by
then. Sources that have not completed by 5:00am are noted in the brief's metadata as
`sources_missing: [...]`; the brief generates with whatever data is present. Missing
sources are flagged in citations metadata (not surfaced to the user unless all sources
are missing). The next scheduled run of those sources proceeds normally; no special
retry logic blocks the brief.

**Why — 5:30am ET:** The target subscriber is a serious defense/energy investor or
analyst who reads intelligence before market prep — by 6am or 7am ET at the latest.
Competitive intelligence products (Defense News Morning Brief, Axios Pro, Politico
Playbook, Bloomberg morning letters) publish by 6am ET. A 6:30am generation window
produces a brief at ~6:45am, missing the early-morning reading window entirely. A
5:30am generation window produces a brief by ~5:45am — ready when subscribers start
their day. EDGAR's overnight batch (8-Ks, bulk filings) is available by 4–5am ET;
DoD contracts, USAspending, and SAM.gov cover prior-day activity and are available
overnight. No meaningful data is lost vs. a later cutoff.

**Why — macro releases are handled separately:** Scheduled macro releases (CPI, FOMC
statements, jobs reports) land at 8:30am ET on known dates. These are tracked in the
`calendar_events` table and trigger a targeted fetch + incremental brief update at
their release time — they do not delay the morning generation window.

**Why — generate-with-available-data:** Blocking generation until all sources respond
allows a single flaky source to delay the brief indefinitely. Sources are independently
circuit-broken (D004); the brief's value comes from synthesis across multiple
corroborating sources, not any single one.

**Cycle 2 — two-window model:** Once the engine is validated, move to two generation
cycles per day: (1) **Morning brief at 5:30am ET** — overnight data, prior-day awards
and filings; (2) **Intraday update at 3:00pm ET** — macro releases, intraday 8-Ks,
congressional activity, earnings. This is how professional intelligence products
operate at scale. Cycle 1 runs one window only.

---

## D015 — Admin interface: Supabase Studio + FastAPI endpoints at MVP

**Decision:** The `resolution_queue` table is an **async audit log**, not a daily work
queue. Low-confidence mentions are auto-dismissed by the resolver cascade (D027) and
logged with `status = 'auto_dismissed'`; no human action is required to keep the
pipeline running. The FastAPI admin endpoints (`GET /admin/resolution-queue`,
`POST /admin/resolution-queue/{id}/resolve`) and Supabase Studio provide access for
**periodic audit** (weekly, monthly, or when a brief output looks wrong) — not daily
triage. Operational metrics (source health, circuit breaker state, LLM spend, last
successful brief) are surfaced via `GET /admin/status`. Sentry handles real-time
alerting. No dedicated admin UI in Cycle 1.

**Why:** A solo operator cannot babysit a daily resolution queue. The two-tier LLM
cascade (D027) handles the vast majority of mentions automatically. Defense contractor
data resolves deterministically via the crosswalk spine for all major primes and
subcontractors; the LLM cascade handles edge cases. Only truly unresolvable mentions
(confidence < 0.55) are auto-dismissed — these are typically obscure foreign entities
or non-standard contractor references that add marginal value to the brief anyway.
The audit log accumulates these for review at the operator's discretion.

*(Updated 2026-06-05: resolution_queue reclassified from daily work queue to async
audit log. Reflects D027 two-tier LLM cascade decision.)*

---

## D016 — Citation faithfulness threshold: 0.95, configurable *(added 2026-06-05)*

**Decision:** The minimum citation-faithfulness score for a brief to publish is **0.95**.
Stored in environment variable `BRIEF_FAITHFULNESS_THRESHOLD` (default `0.95`); adjustable
without a code change.

**What 0.95 means concretely:**

The eval gate checks every cited claim in the brief:
- Prose claims: LLM entailment check ("does this source passage support this claim?") → pass/fail
- Numeric claims: exact match against the cited source value → pass/fail

`faithfulness_score = passing_checks / total_checks`

A brief with 20 citations where 19 pass scores 0.95 → publishes. Where 18 pass → 0.90 →
fails, D013 fallback activates, Sentry alert fires.

**Why 0.95:** A credibility product that publishes uncited claims loses its core
differentiator. 95% means at most 1 claim in 20 is unsupported — tight enough to be a
meaningful guarantee, loose enough not to block every brief on a minor extraction edge
case. The threshold is a variable so it can be tightened toward 1.0 as the pipeline
matures. Starting below 0.95 is not recommended; the eval harness exists to enforce the
guarantee, not to waive it.

---

## D017 — PDF generation: WeasyPrint *(added 2026-06-05)*

**Decision:** Brief PDF export uses **WeasyPrint** (Python library, HTML/CSS → PDF).
Generated on demand in `hpi-api`, cached in Supabase Storage after first generation.
PDF is a Pro-tier feature.

**Why WeasyPrint over Puppeteer:** Puppeteer (headless Chromium) requires 500MB–1GB RAM —
incompatible with `shared-cpu-1x` Fly.io instances without a significant memory upgrade.
WeasyPrint runs in-process (~80MB RAM), handles CSS3 sufficiently for structured documents,
and produces clean output. A defense brief — headline, items, citations — is a structured
document, not a complex web application. No additional service or container required.

**Upgrade path:** If PDF fidelity requirements grow beyond WeasyPrint's CSS support, the
replacement is a dedicated Gotenberg container (headless Chrome via Docker, separate
Fly.io service). This is a deployment change, not a code change — PDF generation is
behind a single function abstraction.

---

## D018 — OAuth providers: Google + GitHub in Cycle 1 *(added 2026-06-05)*

**Decision:** Supabase Auth supports email/password plus the following OAuth providers.
Scope by cycle:

- **Cycle 1:** Google, GitHub
- **Cycle 2:** LinkedIn (OIDC), Microsoft/Azure AD
- **Required for App Store (Cycle 2):** Apple Sign-In (App Store mandate when any social
  auth is offered)

**Why Google + GitHub:** Google covers the broadest professional audience (Workspace,
Gmail). GitHub signals technical and analytical users aligned with the product's positioning.
Both require nothing more than adding credentials in the Supabase dashboard. LinkedIn is
the most professionally relevant network for the HPI audience but is deferred to Cycle 2.
Microsoft/Azure AD targets enterprise users at defense and energy companies — deferred
until there is evidence of enterprise demand.

---

## D019 — Pricing and trial *(added 2026-06-05; payment processor superseded by D050 — Lemon Squeezy. Pricing/trial terms unchanged)*

**Decision:**
- **Free tier:** daily brief (current day only); no archive, no entity 360, no PDF, no follows
- **Pro tier:** $19/month or $179/year (~21% savings, ~$14.92/month effective)
- **Trial:** 14-day free Pro trial, credit card required on sign-up; Stripe `trialing`
  status; auto-converts to paid at trial end unless cancelled

**Why $19/month:** Below the psychological threshold for a professional trying a new tool.
Above commodity newsletter pricing. Competitive with niche intelligence products
($10–$50/month). Positions HPI as a credible product at an accessible launch price.
Prices can be raised after value is proven; lowering later signals distress.

**Why annual at $179:** ~21% discount drives annual commitment and improves cash flow.
At $179/year the subscriber makes one decision and forgets about it — lower churn than
monthly billing.

**Why CC-required trial:** Free trials without CC convert at ~2–5%. CC-required trials
convert at 40–60% because users who sign up have already committed psychologically. For
a solo operator with no marketing budget, conversion efficiency matters more than
top-of-funnel volume.

**Why daily brief on free tier:** The incremental LLM cost of serving an additional free
reader is zero (shared output, D003). Withholding the brief from free users reduces
product value without reducing costs. Differentiation via archive access, entity 360,
PDF, and follows is sufficient to drive Pro conversion.

**Review trigger:** Revisit pricing after 50 paying subscribers or 6 months post-launch,
whichever comes first.

---

## D020 — Frontend tech stack *(added 2026-06-05)*

**Decision:** Next.js App Router (already locked) with the following additions:

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Components | shadcn/ui | Radix primitives (accessible), copy-paste ownership, full customization, excellent App Router support |
| Styling | Tailwind CSS | Utility-first, pairs perfectly with shadcn, dark mode via `dark:` prefix when needed |
| Icons | lucide-react | Already in shadcn dependency tree; consistent, well-maintained set |
| Mutations / cache | TanStack Query v5 | Better mutation + optimistic update handling than SWR; built-in devtools |
| Auth client | @supabase/ssr | Current Supabase package for App Router; `@supabase/auth-helpers-nextjs` is deprecated and must not be used |
| Fonts | next/font | Zero layout shift, no external requests; loads Playfair Display, Lora, Inter |
| Analytics | PostHog | `'use client'` provider wrapper in root `layout.tsx`; auto-tracks page views |
| Error tracking | Sentry | Both API and frontend; initialized in `instrumentation.ts` |

**Why shadcn over MUI/Chakra:** Shadcn components live in the repo — no dependency on a library's release cycle, no override battles, no design system compromise. For a product where visual sophistication is a differentiator, full design ownership is worth the additional setup cost.

---

## D021 — Design aesthetic: clean/editorial, high-class *(added 2026-06-05)*

**Decision:** Clean/editorial visual language as the default. Dark mode deferred to Cycle 2 as a Pro feature.

**Design language:** "Premium intelligence publication" — The Economist's restraint, Stratfor's analytical weight, Bloomberg's data precision. Every element earns its place. Typography carries the design; color signals meaning, not decoration.

**Typography:**
- Display / brief headlines: **Playfair Display** (serif, editorial, expensive-feeling)
- Brief body copy: **Lora** (readable serif at paragraph sizes, pairs with Playfair)
- All UI chrome: **Inter** (clean, modern, versatile)
- All loaded via `next/font` for zero CLS

**Color palette (light mode):**
- Background: `#FAFAF8` (warm white — editorial, not clinical)
- Surface: `#FFFFFF` (cards against warm background)
- Brand primary: `#1B3A6B` (deep navy — authoritative, defense-adjacent)
- Brand secondary: `#C8A96E` (antique gold — premium signal, used sparingly)
- Interactive: `#2563EB` (blue — links, CTAs)
- Foreground: `#1A1A1A` (near-black for maximum readability)
- Full palette and token definitions in `DESIGN_SYSTEM.md`

**Why warm white over pure white:** Pure white (#FFFFFF) reads as clinical and cheap against dark text. Warm white (#FAFAF8) signals print editorial (Financial Times salmon, cream newspaper stock). Subtle but effective.

**Dark mode:** Token architecture supports dark mode from day one (CSS custom properties). Implementation deferred to Cycle 2 — the editorial light experience is the product's visual identity at launch.

---

## D022 — Frontend data fetching pattern *(added 2026-06-05)*

**Decision:** Server Components for all content; Client Components for all interactivity; TanStack Query for mutations and cache invalidation.

**Rules:**
- Server Components (default): fetch from FastAPI directly on the server. Use for all pages where content is the primary load (brief reader, entity 360, marketing home, archive). No loading spinners for initial paint; SEO-ready.
- Client Components (`'use client'`): only when browser APIs, event handlers, or React state are required. Nav auth state, citations drawer, follow button, trial banner, theme toggle.
- TanStack Query: mutations only (follow/unfollow, subscription status revalidation after Stripe redirect). Not used for initial page data — that's Server Components.
- Next.js middleware (`middleware.ts`): calls Supabase `updateSession()` on every request to keep the auth cookie fresh. Runs at the edge.

**Why not client-side fetch for briefs:** A brief page that shows a loading skeleton before content appears signals "this is a web app." A brief page that renders the full content on first paint signals "this is a publication." The product's positioning demands the latter.

---

## D023 — Brief reader layout and navigation *(added 2026-06-05)*

**Decision:** Single column on mobile and tablet; optional right sidebar at `lg:` (1024px+). Slide-in citations drawer on all breakpoints (right panel on desktop, full-screen sheet on mobile).

**Brief reader layout:**
- Content column: `max-w-[72ch]` centered, generous vertical padding
- Sidebar (lg+): catalyst calendar widget + followed entities list (Pro); `w-80` fixed width
- No horizontal scroll; no fixed side nav (wastes screen real estate on a reading product)

**Citations drawer:**
- Triggered by clicking any citation chip `[1]` in brief body
- Desktop: fixed right panel, `w-[420px]`, slides in from right, does not push content
- Mobile: shadcn `Sheet` full-screen bottom or side, same content
- Close: X button, click-outside, or Escape key
- Drawer is scoped to the current brief item's citations by default; "Show all sources" toggle

**Brief item type badges:** Color-coded by item type (Award = navy, Filing = blue, Policy = amber, Macro = teal, Signal = violet) using desk-aware Tailwind variants.

---

## D024 — Subscription UX: trial, upgrade prompts, gates *(added 2026-06-05)*

**Decision:** Inline soft gates over hard redirects. Trial countdown in nav. No hard gate for free tier (current brief always accessible).

**Trial banner:** Displayed only in the NavBar during an active trial. Subtle — "Trial: N days remaining · Manage." Upgrades to slightly more prominent on the last day. Disappears after conversion or cancellation. Not shown on every page as a banner.

**Archive gate (free user, historical brief):** Inline `UpgradePrompt` component above the locked item — not a redirect. "Access the full 90-day archive with Pro. 14-day free trial, cancel anytime." + CTA button. Keeps the user on the product.

**Entity 360 gate (free user):** Full-page `ArchiveLock` component — soft gate with trial CTA. The page route is accessible but the content is replaced with the gate. No hard 403 redirect for web navigation (FastAPI returns 403 on the data endpoint; the UI shows the gate page).

**PDF gate:** Inline tooltip/popover on the PDF button: "PDF export is a Pro feature. Start your free trial." Does not navigate away.

**Post-lapse:** Free tier after trial ends. No hard gate. Current day's brief accessible. Archive items show lock icon + "Pro" label. Product sells itself.

**Stripe Checkout flow:** `/subscribe` → Stripe hosted checkout (redirect) → `/subscribe/success` (confirmation + onboarding + CTA) or `/subscribe/cancel` (no-friction return to `/subscribe`).

---

## D025 — Python project structure: uv, Python 3.12, monorepo workspaces *(added 2026-06-05)*

**Decision:**

- **Package manager:** `uv` (fast, modern, standard for new Python projects in 2025–2026)
- **Python version:** 3.12
- **Repository layout:**

```
HardPowerIntelligence/
  web/           # Next.js (Vercel)
  api/           # FastAPI app — hpi-api Fly.io service
  engine/        # Intelligence engine — shared Python package
  worker/        # hpi-worker entry point (procrastinate runner)
  tests/         # pytest suite (unit + integration)
  supabase/      # Supabase CLI migrations
  docker/        # Fly.io Dockerfiles (Dockerfile.api, Dockerfile.worker)
  pyproject.toml # Root workspace — declares api, engine, worker as members
```

- **One root `pyproject.toml`** with `uv` workspaces. `engine/` is a workspace member
  installable as an editable package by both `api/` and `worker/`. Each service declares
  `engine` as a local dependency.
- **pytest** lives at root; discovers `tests/` directory. All Python tooling (`ruff`,
  `mypy`, `pytest`) configured in root `pyproject.toml`.

**Why:** A monorepo with workspaces means `engine/` code is shared without publishing
to PyPI or duplicating code. `uv` resolves dependencies faster than pip and provides
a lockfile (`uv.lock`) for reproducible builds. Single `pyproject.toml` at root means
one config file for all Python tooling.

---

## D026 — Embedding model: OpenAI text-embedding-3-small *(added 2026-06-05)*

**Decision:** Use OpenAI `text-embedding-3-small` for all vector embeddings:
`entity_aliases.embedding` and `normalized_records.embedding`. Confirms `VECTOR(1536)`
in the database schema. Adds OpenAI as a dependency with `OPENAI_API_KEY` in env.

**Cost:** $0.02 per 1M tokens. Embedding all defense contractor aliases and text chunks
costs cents per month at MVP scale — negligible.

**Usage in the pipeline:**
- Entity resolution: embed `alias_normalized` text at alias creation time
- RAG ingestion: embed `text_chunk` at normalization time (async, post-ingestion)
- RAG query: embed concatenation of top-5 materiality candidate headlines + entity names
  once per brief generation cycle; use as `pgvector` query vector

**Why over alternatives:** `text-embedding-3-small` is the de facto standard for RAG
pipelines — ubiquitous documentation, excellent pgvector compatibility, and the 1536
dimension size is well-supported by `ivfflat` and `hnsw` indexes. Alternatives (Cohere,
local models) add either cost or infrastructure overhead without meaningful quality gain
for this use case.

**Environment variables:**
```
OPENAI_API_KEY=sk-...
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
```

---

## D027 — Entity resolution: two-tier LLM cascade, async audit log *(added 2026-06-05)*

**Decision:** Four-tier automated resolution cascade. No daily human action required.
`resolution_queue` is an async audit log, not a work queue (see updated D015).

```
similarity ≥ 0.92             → auto-link (no LLM)
0.70 ≤ similarity < 0.92      → DeepSeek V4 Flash disambiguation
0.55 ≤ similarity < 0.70      → DeepSeek V4 Flash with expanded context
similarity < 0.55             → auto-dismiss, log to resolution_queue
```

**Environment variables:**
```
ENTITY_RESOLUTION_HIGH_THRESHOLD=0.92
ENTITY_RESOLUTION_MEDIUM_THRESHOLD=0.70
ENTITY_RESOLUTION_LOW_THRESHOLD=0.55
```

**Why the two LLM tiers:** The first LLM call receives the normalized mention +
the top candidates + a short context snippet. The second call (0.55–0.70 range) adds
the full source passage — more context improves accuracy for edge cases without doubling
cost on the common case. Below 0.55, even expanded context rarely resolves correctly;
auto-dismiss is the correct call.

**Why auto-dismiss over provisional entities:** Creating provisional entity nodes risks
polluting the graph with duplicates or incorrect entries that silently corrupt future
briefs. An auto-dismissed mention is a recoverable gap; a wrong entity link is an
active error. The crosswalk spine (USAspending UEI → SAM entity hierarchy) handles all
major defense primes and subcontractors deterministically. Auto-dismissed mentions in
Cycle 1 will predominantly be obscure foreign entities or non-standard contractor
references — marginal value to the brief.

---

## D028 — Synthesis prompt structure *(added 2026-06-05)*

**Decision:** Dual-section prompt with `[CITE:N]` sequential citation index and
structured JSON output format.

**Prompt structure:**
```
## Verified facts (ground truth — do not contradict or modify)
[JSON array: {record_id, entity, amount, date, program, source_id}]

## Source passages (cite by index)
[1] {source_id, date, url} — "{excerpt}"
[2] ...

## Output schema
{
  "headline": "...",
  "bluf": "...",
  "items": [
    {
      "item_type": "award|filing|policy|macro|signal",
      "headline": "...",
      "body": "... [CITE:1] ... [CITE:3] ...",
      "entity_mentions": ["..."],
      "citation_indices": [1, 3]
    }
  ]
}

## Instructions
Write a Defense brief. Every factual claim must include [CITE:N].
Only reference facts and passages provided above.
Return valid JSON matching the output schema exactly.
```

**Citation binding:** The `[CITE:N]` indices map to `raw_record_id` at position N-1 in
the sources list. The binding step resolves indices to UUIDs and creates `citations`
rows. Any claim without a `[CITE:N]` marker is flagged as an uncited claim and counts
against the faithfulness score.

**Why structured JSON:** Prose output with post-processing parsing is fragile. Telling
the model the exact output schema and validating the response with Pydantic is reliable
with current-generation LLMs. The `DeepSeek V4 Pro` and `Qwen3.7 Max` models both
handle JSON schema adherence well with explicit schema instructions.

**Why dual-section:** Separating structured facts from text passages makes the
"non-hallucinable spine" explicit to the model. Structured facts (amounts, dates,
entity IDs) are labeled as ground truth; passages are labeled as supporting color.
This reduces factual hallucination and makes the eval gate's entailment check
more interpretable — the eval model can distinguish fact violations from passage
interpretation errors.

---

## D029 — Eval gate architecture *(added 2026-06-05)*

**Decision:** Per-item evaluation (one Qwen3.7 Max call per brief item). Item-level
exclusion for failed items. Brief-level `faithfulness_score` computed over surviving
items only.

**Eval call structure per item:**
```json
{
  "claims": [
    {"id": "c1", "text": "Lockheed Martin was awarded $1.1B for LRASM production"},
    {"id": "c2", "text": "The contract runs through FY2028"}
  ],
  "sources": [
    {"index": 1, "excerpt": "Award amount: $1,100,000,000; LRASM production FY26-28"}
  ],
  "task": "For each claim, determine if it is supported by the provided sources."
}
```

**Expected JSON response:**
```json
{
  "verdicts": [
    {"id": "c1", "verdict": "pass", "confidence": 0.98},
    {"id": "c2", "verdict": "pass", "confidence": 0.91}
  ]
}
```

**Failure handling:**
- All claims in an item fail → item excluded from published brief, logged
- `faithfulness_score = total_passing_claims / total_claims` across remaining items
- Score ≥ `BRIEF_FAITHFULNESS_THRESHOLD` (0.95) → brief publishes
- Score < threshold → D013 fallback (previous brief + staleness indicator + Sentry alert)

**Why item-level exclusion over brief-level failure:** One bad extraction (e.g., a
garbled EDGAR filing parse) should not block an otherwise credible brief. Item-level
exclusion is the right granularity — surgical removal of the problematic item, not
throwing out the whole output.

---

## D030 — Materiality scoring formula *(added 2026-06-05)*

**Decision:**

```python
materiality = (
    SOURCE_WEIGHTS[source_id]       * 0.25 +   # authority
    float(is_new_since_last_brief)  * 0.30 +   # novelty (binary)
    normalize(amount_usd)           * 0.20 +   # magnitude (0.0 for non-numeric)
    ENTITY_IMPORTANCE[entity_type]  * 0.15 +   # importance
    min(corroboration_count, 3)/3   * 0.10     # corroboration (capped at 3)
)
```

Candidates with `materiality < MATERIALITY_THRESHOLD` are dropped before synthesis.

**Environment variables (all tunable without code changes):**
```
MATERIALITY_THRESHOLD=0.35

SOURCE_WEIGHTS={"usaspending": 0.9, "dod_contracts": 0.85, "edgar": 0.85,
                "sam_gov": 0.8, "congress_gov": 0.8, "fred": 0.7, "gdelt": 0.5}

ENTITY_IMPORTANCE={"company": 1.0, "program": 0.85, "person": 0.7,
                   "gov_agency": 0.75, "institution": 0.6, "sector": 0.5}
```

**`normalize(amount_usd)`:** min-max normalization against a rolling 90-day window of
award amounts for the same source. Awards in the top decile score 1.0; median score
~0.5; no amount scores 0.0.

**Review cadence:** Weights are starting estimates. After 30 published briefs, review
the materiality distribution — if the threshold is too loose (too many items per brief)
or too tight (brief feels thin), adjust `MATERIALITY_THRESHOLD` first before touching
component weights.

---

## D031 — RAG retrieval parameters *(added 2026-06-05)*

**Decision:**

- **Time window:** all `normalized_records` with `created_at >= last_published_brief.generation_started_at`. Ensures no data is missed on brief failure days (D013).
- **Passage count:** `RAG_PASSAGE_TOP_K=20` (configurable; max 40 before prompts become unwieldy)
- **Graph edge cap:** top 50 edges by `(transaction_time DESC, confidence DESC)` for all entities in the candidate pool; `RAG_GRAPH_EDGE_LIMIT=50`
- **Query vector:** embed the concatenation of the top-5 materiality candidates' headlines + primary entity names. Single `text-embedding-3-small` call per brief generation cycle. Query: `ORDER BY embedding <=> $query_vector LIMIT RAG_PASSAGE_TOP_K`

**Why top-5 candidates as query:** After change detection and materiality scoring, the
top-5 candidates define "what today's brief is about." Embedding their headlines +
entities as a single query string retrieves the most relevant supporting passages
without additional LLM calls or per-candidate queries. This is the minimal-cost
approach that captures the day's thematic focus.

**Environment variables:**
```
RAG_PASSAGE_TOP_K=20
RAG_GRAPH_EDGE_LIMIT=50
```

---

## D032 — Database migrations: Supabase CLI *(added 2026-06-05)*

**Decision:** All schema changes via Supabase CLI migration files. No manual SQL in
production. No Alembic.

```
supabase/
  migrations/
    20260605000001_initial_schema.sql
    20260605000002_procrastinate_schema.sql
    ...
  config.toml
  seed.sql      # source_registry seed rows
```

**Workflow:**
- Local development: `supabase start` (local Postgres + Auth + Storage emulator)
- New migration: `supabase migration new <description>`
- Apply locally: `supabase db reset` (drops + recreates from migrations)
- Deploy to cloud: `supabase db push`
- All migration files committed to git

**Why Supabase CLI over Alembic:** Supabase CLI is purpose-built for Supabase projects,
handles RLS policies and Auth schema correctly, and provides the `supabase start` local
emulator that matches production exactly. Alembic is better suited to SQLAlchemy-centric
projects where Python models drive the schema. This project drives schema from SQL DDL
(DATABASE_SCHEMA.md), making Supabase CLI the natural fit.

---

## D033 — Test infrastructure: pytest, asyncio, golden fixtures *(added 2026-06-05)*

**Decision:**

```toml
# pyproject.toml [tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "--cov=engine --cov=api --cov-report=term-missing"
```

**Dependencies:** `pytest`, `pytest-asyncio`, `pytest-cov`, `respx` (async HTTP mocking for adapters)

**Test structure:**
```
tests/
  unit/                          # No network, no DB — golden fixtures only
    adapters/
      test_usaspending_adapter.py
      test_edgar_adapter.py
    entity/
      test_resolver.py
    brief/
      test_generator.py
      test_citation_eval.py
  integration/                   # Requires local Supabase (supabase start)
    test_ingestion_pipeline.py
    test_entity_resolution_e2e.py
  fixtures/
    usaspending/
      20260605_dod_awards_response.json   # recorded real API response
    edgar/
      20260605_8k_lmt.json
    sam_gov/
      20260605_entity_lmt.json
  conftest.py                    # DB fixture, mock HTTP client, sample entities
```

**Gate 4 acceptance:** unit tests only (golden fixtures). Integration tests are
good practice but not required to pass Gate 4. Gate 5 (brief verified) requires
the eval harness to pass on at least one real brief — integration test territory.

**Golden fixture convention:** Record a real API response once (during adapter
development), save to `tests/fixtures/{source_id}/{date}_{description}.json`,
never regenerate automatically. Fixtures are version-controlled truth for the parser.
Update manually only when the upstream API changes its response format.

---

## D034 — Embedding bootstrap: inline at brief generation time *(added 2026-06-06)*

**Decision:** `embed_pending_records(pool, since: datetime)` runs as the first step
of the brief generator. It batch-calls OpenAI `text-embedding-3-small` for any
`normalized_records` in the time window where `embedding IS NULL`. Synchronous-inline
at MVP. Formalized move to the async procrastinate worker is a Gate 6 task.

**Why:** No prior step generates embeddings. The RAG cosine-search step requires
`embedding IS NOT NULL` to return results. Making this the first generator step
ensures the window's records are always embedded before retrieval, with negligible
cost (~20 records × 200 tokens ≈ $0.0004 per brief).

**Gate 6 follow-up:** Add `@app.periodic` embedding task that runs post-ingestion so
embeddings exist before the brief window opens, eliminating brief-generation latency.

---

## D035 — Magnitude normalization fallback for thin history *(added 2026-06-06)*

**Decision:** `normalize(amount_usd)` uses the rolling 90-day min-max per D030
when the window has ≥ `MAGNITUDE_MIN_WINDOW` (default 10) records with a non-null
amount. When the window is thin, fall back to a static bucket scale:
`<$10M → 0.2`, `$10M–$100M → 0.4`, `$100M–$1B → 0.7`, `$1B+ → 1.0`.
Records with no amount score 0.0 in either mode.

**Why:** The first-ever brief run has no 90-day history. A divide-by-zero or null
magnitude score would break materiality scoring for all records. The bucket scale
is deterministic, explainable, and directionally correct.

**Environment variable:** `MAGNITUDE_MIN_WINDOW=10`

---

## D036 — Corroboration fallback when entity_id is NULL *(added 2026-06-06)*

**Decision:** `corroboration_count` for a record = number of other records in the
time window that share at least one `entity_id` (preferred) OR, when `entity_id IS
NULL`, share at least one exact-match `normalized_mention` string after applying
`normalize_mention()`. This is documented as a degraded-mode behavior that improves
automatically as entity resolution populates `entity_id` values.

**Why:** Gate 5 runs before the entity graph is seeded with crosswalk data. Most
`entity_mentions[*].entity_id` fields will be NULL. Without a fallback, all
corroboration scores are 0, making the 10% corroboration component useless for
the first brief.

---

## D037 — LLM client module: engine/llm/client.py *(added 2026-06-06)*

**Decision:** All LLM text-generation calls (synthesis, eval, entity disambiguation)
go through `engine/llm/client.py`. Interface:

```python
async def complete(
    model: str,
    messages: list[dict],
    json_mode: bool = True,
    fallbacks: list[str] | None = None,
) -> str:  # returns the content string
```

Internals: LiteLLM `acompletion()` with `response_format={"type": "json_object"}`
when `json_mode=True`. On JSON parse failure, one repair retry with an explicit
"return only valid JSON" message appended. After retry failure, raises to trigger
LiteLLM fallback. Token counts and estimated cost logged via structlog on every call.

**Why:** Centralises retry logic, JSON enforcement, cost logging, and the LiteLLM
dependency. If LiteLLM ever requires migration, only this file changes.

---

## D038 — Eval claim extraction: sentence-boundary split *(added 2026-06-06)*

**Decision:** Claims are extracted from `brief_item.body` by splitting on sentence
boundaries (`re.split(r'(?<=[.!?])\s+(?=[A-Z])', body)`). Each sentence is one
claim. Sentences with no `[CITE:N]` marker auto-fail. All claims — including numeric
— are evaluated by Qwen3.7 Max entailment check. No separate exact-match path for
numeric claims (premature optimization; revisit at Gate 6 if eval costs grow).

All claims for one brief_item are batched into a single Qwen call returning structured
JSON: `{"claim_evaluations": [{"id": "c1", "supported": bool}]}`.

**Why:** Sentence = claim maps cleanly to the synthesis prompt instruction ("one
citation per sentence"). LiteLLM approach consistent. Numeric exact-match adds
implementation complexity without demonstrated benefit at MVP scale.

---

## D039 — Brief item bounds *(added 2026-06-06)*

**Decision:** `BRIEF_MAX_ITEMS=8`, `BRIEF_MIN_ITEMS=3`. The synthesis prompt targets
5–7 items. If fewer than `BRIEF_MIN_ITEMS` survive both materiality scoring and the
eval gate, `briefs.status` is set to `failed` and the D013 fallback (previous
published brief + staleness indicator) is served.

**Why:** A one- or two-item brief is not a viable intelligence product. Eight items
is the practical upper bound for a focused BLUF brief that can be read in under five
minutes.

**Environment variables:** `BRIEF_MAX_ITEMS=8`, `BRIEF_MIN_ITEMS=3`

---

## D040 — RAG time window fallback for first brief *(added 2026-06-06)*

**Decision:** When no previously published brief exists (`briefs` table is empty or
has no `status = 'published'` rows), use `now() - BRIEF_WINDOW_HOURS_FALLBACK hours`
as the window start. Default: 48 hours. Subsequent briefs use
`last_published_brief.generation_started_at`.

**Why:** On first run there is no baseline timestamp. A 48-hour window ensures the
first brief has sufficient data without pulling weeks of history.

**Environment variable:** `BRIEF_WINDOW_HOURS_FALLBACK=48`

---

## D041 — PassageContext: immutable citation index *(added 2026-06-06)*

**Decision:** The RAG retrieval step constructs a `list[PassageContext]` (frozen
dataclass: `index, raw_record_id, source_id, url, fetched_at, native_id, excerpt`)
in a single operation and never mutates it. The list index position IS the citation
index (`[CITE:1]` maps to `passages[0]`). This list is passed unchanged from RAG
retrieval → synthesis prompt construction → citation row creation.

**Why:** Mutable reordering or deduplication of passages between retrieval and
citation creation breaks the citation index mapping. Immutability by construction
prevents this class of bug entirely.

---

## D042 — Gate 5 integration run strategy *(added 2026-06-06)*

**Decision:** Gate 5 closes via a one-time manual integration run, not a CI test.
Process:
1. Seed local Supabase DB from the golden USAspending fixture
2. Run `python scripts/run_brief.py --desk defense` (requires `OPENROUTER_API_KEY`)
3. Record results in `EVAL_BASELINE.md`

The script is checked into `scripts/`; the run is not part of the automated test
suite. Integration tests in `tests/integration/` are marked `@pytest.mark.integration`
and skipped by default (`pytest -m "not integration"`).

**Why:** EVAL_BASELINE.md requires real LLM outputs. Running real LLM calls in CI
introduces cost, flakiness, and API key management complexity not justified at this
stage.

---

## D043 — Shared asyncpg pool factory *(added 2026-06-07)*

**Decision:** Connection pooling lives in `engine/engine/db.py` as an async
`create_pool()` factory that strips the `+asyncpg` prefix from `DATABASE_URL`. Both
FastAPI (lifespan-managed) and worker/script code import from there. No ad-hoc pool
creation scattered across scripts.

**Why:** DRY connection management; one place to tune pool size, timeouts, and codecs.

---

## D044 — Gate 6 closure criteria *(added 2026-06-07)*

**Decision:** Gate 6 (`web_reader_live`) closes when (a) `pytest -m "not integration"`
passes, (b) `tsc --noEmit` passes in `web/`, and (c) the required pages exist and
TypeScript-compile cleanly. Visual verification is manual against local Supabase data.
Playwright end-to-end tests are deferred to Gate 7 (`tests_passing`).

**Why:** Gate 8 is `deploy_ready`; Gate 6 means "functionally complete and verified
locally," not deployed. TypeScript compilation is the cheap, high-value gate for a
frontend; browser automation is heavier infrastructure better suited to Gate 7.

---

## D045 — Checkout graceful degradation *(added 2026-06-07)*

**Decision:** The subscribe page UI ships complete in Gate 6. The checkout action only
fires when payment credentials are present in the environment; absent credentials, the
CTA surfaces an explicit "payments not yet configured" state rather than crashing.

**Why:** Unblocks the gate without requiring live payment-processor configuration, which
is a Gate 8 launch concern.

---

## D046 — Tailwind / shadcn version policy *(added 2026-06-07)*

**Decision:** Use whatever `shadcn@latest init` installs (Tailwind v4 + CSS-first config
expected as of 2026). The DESIGN_SYSTEM.md token values are CSS custom properties and
translate directly into the installed version's config format — same values, adapted
syntax. Pin the installed versions in `package.json`.

**Why:** Forcing the Tailwind v3 config format the spec was written against would fight
the tooling for no benefit. Tokens are syntax-portable; the values are what matter.

---

## D047 — Gate 6 component depth *(added 2026-06-07)*

**Decision:** Functional in Gate 6: `NavBar`, `Footer`, `BriefHeader`, `BriefItem`,
`CitationsDrawer`, `PricingTable`, `LoginForm`, `SignupForm`, Supabase `middleware.ts`.
Functional stubs (render, no live data wiring): everything entity-related
(`EntitySearch`, `FollowButton`, `EntityChip`, Entity 360) and PDF export.

**Why:** Entity features depend on the entity graph (Gate 4 incomplete) and PDF depends
on WeasyPrint (unbuilt). Stubbing them keeps the gate honest while preserving layout.

---

## D048 — Local Supabase for Gate 6 development *(added 2026-06-07)*

**Decision:** All Gate 6 development runs against the local Supabase stack
(`supabase start`, ports 54321/54322), never the cloud project. FastAPI verifies JWTs
with the local `SUPABASE_JWT_SECRET` from `supabase status`; Next.js auth points at
`http://127.0.0.1:54321`. Cloud values are swapped in only at deploy (Gate 8).

**Why:** Local and production stay fully isolated — no risk of corrupting cloud data
during development. Confirmed by user 2026-06-07.

---

## D049 — Build `/desk/defense` in Gate 6 *(added 2026-06-07)*

**Decision:** Build `web/app/desk/defense/page.tsx` (the primary daily reader) as part
of Gate 6 even though it is not in the original gate artifact list. It shares all
components with `/brief/[id]`; the only delta is the API call
(`GET /briefs/latest` vs `GET /briefs/{id}`).

**Why:** Near-zero marginal cost once `/brief/[id]` exists, and it makes the gate
represent the application actually working rather than three isolated pages.

---

## D050 — Payment processor: Lemon Squeezy (Merchant of Record) *(added 2026-06-07)*

**Decision:** Use Lemon Squeezy as Merchant of Record instead of Stripe. This
**supersedes the Stripe-specific mechanism in D012 and D019** — the pricing ($19/mo,
$179/yr, 14-day CC-required trial) and the dual-layer gating principle (FastAPI gates
data, Next.js gates UX) are **unchanged**; only the processor, webhook source, and
checkout mechanism change.

- Webhook endpoint: `POST /webhooks/lemon-squeezy` (HMAC-SHA256 `X-Signature` verification)
- Checkout: Lemon Squeezy hosted checkout URL/overlay with `custom_data.user_id` embedded
- `subscriptions` table stores Lemon Squeezy subscription IDs

**Why:** HPI is a solo-operated information product with a global audience. The EU/UK
$0 VAT threshold makes Stripe-as-MoR a tax-compliance burden from the first
international subscriber; an MoR absorbs all global VAT/GST/sales-tax liability. The
payment code was not yet written, making this the clean decision window. Lemon Squeezy
is Stripe-owned (Stripe processing infrastructure under an MoR legal shield), and its
webhook handler shape is nearly identical to the Stripe one originally planned. Tradeoff
accepted: higher headline fee (~5% + $0.50 vs ~2.9% + $0.30) in exchange for eliminated
tax-filing labor — the effective gap narrows sharply on international volume.

**Compliance note:** HPI must remain positioned as a general publication, not investment
advice (the disclaimer is already in `FRONTEND_SPEC.md` and the Footer). Avoid
"make money from this data" framing in all marketing copy to pass MoR live-activation
review.

---

## D051 — Parchment-equations atmospheric backdrop *(added 2026-06-10)*

**Decision:** A parchment texture overlaid with accurately-rendered mathematical
equations grouped by the app's four coverage domains (Defense Technology, Space
Exploration, Artificial Intelligence, Energy Technology) becomes a brand motif.

Placement rules:
- **Marketing / hero / auth pages:** full parchment-equations image as the hero
  backdrop (dimmed/overlaid so foreground type stays legible). Overrides the prior
  plain `#FAFAF8` hero background noted in FRONTEND_SPEC.md `GET /` Hero section.
- **App chrome (header / footer / sidebar):** a *hint* of the parchment carried
  through as an accent in the chrome only — e.g. a faint parchment fill or a thin
  equation-edge strip — so the motif persists across authenticated pages.
- **Reading surfaces (brief reader, dashboard, content cards):** stay clean white
  (`--surface` / `--background`). No backdrop behind long-form reading content.

**Why:** The locked design system (Principle 1, "Editorial over app. Decoration is
noise.") forbids busy decoration behind reading content; legibility and the
"premium intelligence publication" restraint win there. But the equation motif is
genuinely on-theme — the four equation groups map 1:1 to the app's coverage areas —
so it earns a place as atmosphere in marketing and as a light accent in chrome,
without touching the reading experience. User-requested 2026-06-10.

**Asset:** Source at repo root `parchment-space-energy-ai.png` (1672×941, RGB).
Staged for the frontend gate at `web/public/textures/parchment-equations.png`.
TODO at frontend build: optimize (WebP/AVIF, the PNG is ~3.2 MB), generate a dimmed
overlay variant for the hero, and a low-opacity chrome-accent crop. Equations should
be verified for accuracy before launch (they are decorative but the brand promise is
"cites its sources" — visibly wrong math undercuts that).

**Status:** Recorded after Gate 6. The frontend (`web/`) was scaffolded in Gate 6
(web reader live), so this is implementable now: wire a `ParchmentBackdrop` into the
hero/auth pages and the chrome accent (footer). Not yet implemented in code.

---

## D052 — Frontend gate is `next build`, not bare `tsc --noEmit` *(added 2026-06-10)*

**Decision:** The Gate 7 frontend type check in `run-tests.sh` runs `next build`
(which performs TypeScript checking) instead of `npx tsc --noEmit`. This **supersedes
the `tsc --noEmit` frontend command specified in D044**; the rest of D044 (Playwright
deferred, backend `pytest -m "not integration"`) is unchanged.

**Why:** The project installed **Next.js 16** (D046 — "use whatever the toolchain
installs"), whose typed-routes feature generates `.next/types/validator.ts`. That file
only type-checks correctly inside `next build`'s Next-plugin-aware TypeScript program.
The `next` entry in `tsconfig.json` `plugins` is a *language-service* plugin — it
augments route-type resolution in editors and during `next build`, but a bare
command-line `tsc --noEmit` does not load it, so the generated validator cannot resolve
the route registry (`AppRoutes` collapses to `never`) and fails with spurious errors
like `Type '"/"' is not assignable to type 'never'` — even though the routes are
registered correctly and `next build` passes its own TypeScript phase. `next build` is
also the authoritative compile (it is what Vercel runs at deploy), so the gate now
matches production truth.

**Also:** `run-tests.sh` backend command changed from `python -m pytest` to
`uv run pytest` so the gate is reproducible from a clean checkout after `uv sync`,
without manual venv activation. Relatedly, the workspace root was missing
`[tool.uv.sources]` (api/worker depend on `hpi-engine`); without it a clean `uv sync`
failed outright. Both were latent because CI runs only `meridian-verify.sh` and never
provisions or runs the Python suite.

---

## D053 — HNSW embedding index (not ivfflat) *(added 2026-06-12)*

**Decision:** The pgvector index on `normalized_records.embedding` is **HNSW**
(`vector_cosine_ops`), not ivfflat. Migration `20260612000001_embedding_hnsw_index.sql`.

**Why:** The first production brief retrieved 0 passages and could not publish. ivfflat
with the default `probes = 1` returns zero rows for an ANN `ORDER BY embedding <=> $vec`
when the table holds very little data (the single probed list is empty). The RAG
retrieval JOINs `raw_records`, which pushed the planner onto the ivfflat index → no
passages → citation eval excluded every item (faithfulness 0.000). HNSW has high recall
out of the box (no `probes` tuning), is correct on small datasets, and scales. After the
swap: 3 passages retrieved, eval 1.000, brief published.

---

## D054 — `pyjwt[crypto]` for asymmetric (ES256) Supabase tokens *(added 2026-06-12)*

**Decision:** The API depends on `pyjwt[crypto]` (pulls in `cryptography`), not plain
`pyjwt`.

**Why:** Cloud Supabase signs user JWTs with **ES256** (asymmetric signing keys); PyJWT
needs `cryptography` to verify ES256/RS256. The dependency was plain `pyjwt`, written and
tested against local Supabase's HS256 (which only needs hmac). In production every
authenticated request failed with 401 `invalid_token` (`MissingCryptographyError`), so
the web reader showed "today's brief is being prepared" despite a published brief. This
is a local-vs-cloud gap that only surfaced against the real cloud auth. `api/app/deps.py`
already supports both paths (JWKS for ES/RS, HS256 fallback); it just lacked the crypto
backend.

---

## D055 — Data-collection architecture: structured-first, news-secondary *(added 2026-06-14)*

**Decision:** The Cycle-2 data pipeline is built on **free, public-domain structured
primary-source data as the spine** (USAspending, SEC EDGAR, EIA, FRED, SAM/TED/SIPRI,
etc.). **News/GDELT is a secondary discovery + corroboration layer and is never the sole
citation for a brief claim.** Settles the open questions in
[`docs/DATA_ARCHITECTURE_ANALYSIS.md`](docs/DATA_ARCHITECTURE_ANALYSIS.md):

- **Cadence:** daily brief (not real-time) → ingestion cadence matched to daily publish.
- **Scope:** global (consistent with the SITREP app); LLM cost held flat via deterministic
  pre-filter (entity allowlist + theme codes + English-tag), not by limiting geography.
- **Spend:** free-first only; paid sources (FMP ~$19/mo, Quiver) stay **revenue-gated**.
- **Product shape:** three desk briefs (Defense / AI / Energy) **plus a cross-domain
  convergence brief** — the moat made visible.
- **Pipeline:** introduce a **`signals`/`events` layer** (dedup-clustered, scored) between
  `normalized_records` and briefs; home for cross-domain `entity_edges`, novelty, confidence.
- **GDELT:** start with the **keyless DOC 2.0 JSON API** (no GCP/billing); BigQuery deferred
  until deeper co-occurrence analytics are wanted.
- **Publishing:** fully autonomous (citation-faithfulness eval, Gate 5, is the quality bar);
  revisit a human-in-the-loop gate only at significant scale.
- **Retention:** 14–30 day **hot window** for `normalized_records` + embeddings; prune/archive
  raw; keep `briefs` + `signals` indefinitely.

**Why:** The cheapest, most defensible, and highest-provenance pipeline are the *same*
pipeline. Structured government/regulatory data is already parsed (low LLM triage cost),
freely redistributable (no licensing risk), and citable as primary fact — whereas a
news-first product pays LLMs to separate signal from a noisy, copyright-encumbered firehose
and is trivially replicable. The moat is the **entity graph + cross-domain edges over free
structured data**, not access to any feed. The bottleneck is the ingestion *harness* (one
adapter, no runner today), so the leverage is building the runner once and making each new
adapter cheap. Cost analysis (global ≈ $0 infra delta; BigQuery ≈ $0 at our scale; Supabase
storage trivial vs. the HNSW vector-index limit) is recorded in §12a of the analysis doc.

---

## D056 — `license_class` + `source_reliability` enforced on every adapter *(added 2026-06-14)*

**Decision:** Every adapter declares a **`license_class`** (`public_domain` / `licensed` /
`scrape_gray`, per `DATA_SOURCES.md`) and a **`source_reliability`** tier (1 primary record /
2 authoritative secondary / 3 discovery-sentiment). Both become fields on `NormalizedRecord`
and the `raw_records`/`normalized_records` tables. Synthesis is **license-aware**: only
`public_domain` text may be republished verbatim; `licensed` and `scrape_gray` sources are
**link-and-cite only** (synthesize from, never quote raw). The citation-faithfulness eval
enforces that a claim cited to a non-public-domain source resolves to a link, not a quoted
block.

**Why:** For a *paid* subscription product, "free to access" ≠ "redistributable." This is the
most under-weighted risk in the raw source survey. Encoding license posture in the data model
(not as tribal knowledge) makes it impossible for restricted text to leak into a published
brief body, and `source_reliability` lets synthesis prefer primary sources and report honest
confidence. Government data being both free *and* freely redistributable is precisely why the
free-first stack (D055) is also the legally safe stack.

---

## D057 — Production ingestion runner design *(added 2026-06-14)*

**Decision:** The production ingestion runner (`engine/ingest/`, driven by
`scripts/run_ingest.py`) is the live-data replacement for `scripts/seed_fixtures.py`
(D004, D055). Concrete design choices:

- **Adapter HTTP contract.** Adapters declare `base_url` + `http_method`; the runner does the
  HTTP via a shared `HttpFetcher` (httpx + tenacity). Retries target *transient* failures
  only — transport errors, 429, 5xx with exponential backoff — and raise immediately on a
  non-retryable 4xx so a broken adapter fails fast. Adapters are looked up by `source_id` in
  `engine/adapters/registry.py` (one line per new source).
- **Deterministic dedup via the DB.** Insert into `raw_records` with
  `ON CONFLICT (source_id, native_id, content_hash) DO NOTHING RETURNING id`; a returned id
  means new, so only **new** raw records get a `normalized_record` and an embedding. Re-runs
  are idempotent and cheap.
- **Accounting first, fail-soft per source.** An `ingestion_runs` row is opened `running`
  before any network call and always closed (`success`/`failed`/`skipped`). An ingestion
  failure is recorded (run + circuit breaker) and returned as `status='failed'` — it does
  **not** raise, so one bad source can't abort a multi-source schedule. Programmer errors
  (unknown source/adapter) still raise.
- **Circuit breaker.** Consecutive failures increment `source_registry.circuit_breaker_*`;
  at the threshold the breaker opens and skips runs for a 30-min cooldown, then allows one
  half-open trial. Success resets it.
- **Embedding in the runner.** New chunks are embedded at ingest time (gated on
  `OPENAI_API_KEY` + an `embed` flag), spreading cost off the brief's critical path; the
  generator's lazy embed becomes a no-op. Reuses `embed_pending_records` (D034).
- **Hot-window retention (D055 §12a).** `prune_hot_window` deletes `normalized_records`
  older than `INGEST_HOT_WINDOW_DAYS` (default 21) outright, and `raw_records` only if
  unreferenced by citations / normalized records / entity edges / resolution queue — so a
  raw record cited by a kept brief is never deleted and citations never dangle.

**Why:** The schema (`source_registry`, `ingestion_runs`, the `raw_records` unique
constraint, `last_cursor`, circuit-breaker columns) was already designed for this in the
initial migration; the runner just operationalizes it. Pushing dedup into the DB's unique
constraint (rather than app-side bookkeeping) makes idempotency a property of the schema, and
fail-soft-per-source is what lets the eventual multi-source daily schedule survive a single
flaky API. Validated: 123 unit tests pass (19 new — fetcher retry/backoff via respx, runner
control-flow + dedup via a fake DB driving the real adapter, retention window math) and a
live no-DB smoke test fetched + parsed 100 real USAspending records through the fetcher.

---

## D058 — Brief reproducibility + citation enforcement on live data *(added 2026-06-14)*

**Decision:** Three changes make brief generation reproducible and reliably faithful once
fed real (not fixture) data:

- **Deterministic generation.** Synthesis *and* eval LLM calls run at `temperature=0`
  (`llm_temperature` setting, plumbed through `LLMClient.complete`).
- **Citation enforcement by sentence-dropping.** After synthesis, any sentence lacking a
  `[CITE:N]` is removed (`strip_uncited_sentences`) and each item's `citation_indices` is
  re-derived from the cleaned body; items left empty are dropped. The published brief
  contains only provable, cited claims.
- **Idempotent persistence.** `persist_brief` deletes any existing `(desk, date)` brief
  (cascades to `brief_items` + `citations`) before inserting, so re-runs replace rather than
  raising `UniqueViolation`, and a passing brief can supersede a failed one.

**Why:** The first live brief run exposed all three. Generation was wildly non-deterministic
— the same data scored **0.000** one run (every item excluded; the model embellished terse
USAspending records with facts like "Management Contract *Extension*" not in the source) and
**0.750** the next (different awards selected, different phrasing). At `temperature=0` the
model selects and phrases consistently and stays faithful to the sparse source text. The
0.750 run still failed the 0.95 gate purely because of one **uncited sentence** dragging an
item to 0.50 — so rather than fail an otherwise-good brief on one stray sentence, we drop the
unsupported sentence (consistent with fully-autonomous publishing, D055 Q7: publish only what
is provable). And the run crashed on persist because a failed brief already held the
`(desk, date)` slot — idempotency was a known D055 gap, now closed. Validated by 9 new unit
tests (sentence-stripping, temperature plumbing, delete-before-insert) and a live re-run.

**Refinement (2026-06-20, Phase 1) — per-source cadence: USAspending uses a rolling lookback, not a
forward watermark.** Phase 1 investigation found USAspending silently fetching **0 records** every run
(`status=success fetched=0`) — which is why no federal awards reached the briefs and entity *minting*
never fired. Root cause: the runner's forward-advancing date cursor (`next_cursor → {last_date: today}`)
works for EDGAR (filings appear same-day) but not for USAspending — awards are filtered by **action
date**, and an award shows up in the API weeks *after* its action date (reporting lag). The watermark
shrank the window to ~1 day, which is reliably empty. Fix: `build_request_payload` now ignores the date
watermark and always queries a **fixed rolling lookback** (`_LOOKBACK_DAYS = 45`); content-hash dedup
(D057) absorbs the repeats. The cursor still walks probe pages; only the date window changed. General
principle recorded: **a lagging source needs a rolling re-query window + dedup, not a forward
watermark.** Also added `scripts/brief_quality_report.py` (read-only) to measure per-desk item/source/
entity mix over a window so this kind of gap surfaces as data, not anecdote.

---

## D059 — Desks are scoped by technology theme, not agency *(added 2026-06-14)*

**Decision:** The **Defense desk = "Defense Tech," defined thematically and cross-agency** —
space/satellites, directed energy/lasers, drones/counter-UAS, surveillance/ISR, autonomy,
robotics, missiles/hypersonics, electronic warfare, radar — *wherever* funded (DoD, DHS,
DOE/NNSA, NASA, intel), explicitly **not** DoD-only. Generic federal overhead (IT services,
admin, emergency management) is out. The same thematic-scoping pattern will define the AI and
Energy desks. Implemented as a **deterministic thematic pre-filter** on the USAspending
adapter: a PSC-informed keyword list (`_DEFENSE_TECH_KEYWORDS`) passed to the API's `keywords`
filter, plus a 7-day lookback (the filter narrows results, so widen the window).

**Why:** The first live brief surfaced DHS ICE IT support, FEMA emergency management, and GSA
IT services under "Defense" — faithfully cited but off-topic, because the adapter pulled the
top awards by dollar amount across *all* agencies with no thematic filter. The fix is not an
agency filter (a DHS border-surveillance drone *is* defense tech; a generic DoD IT contract is
not) but a **technology-relevance** filter. USAspending's keyword search indexes PSC/NAICS code
*descriptions*, so PSC-informed keywords ("guided missile" → PSC 1410, "radar" → PSC 5840s)
act as a cross-agency category filter in one query, while emerging terms PSC codes lag
("directed energy", "autonomous", "hypersonic", "machine learning") are caught directly. This
is the deterministic pre-filter from `DATA_ARCHITECTURE_ANALYSIS.md` §4 — relevance enforced
before anything reaches the LLM (cheaper + sharper). The API AND-combines `psc_codes` and
`keywords`, so true "PSC OR keyword" would need two merged queries; a literal `psc_codes`
second query is a documented future upgrade if keyword precision proves insufficient.
Validated live: the filter replaced the generic-IT results with NASA space programs, Boeing/
Lockheed space systems, Harris radar, and BlueStaq space-situational-awareness awards.

---

## D060 — Product north-star: the Defense-Tech ∩ AI ∩ Energy convergence *(added 2026-06-14)*

**Decision:** The product is organized around the **tri-sector convergence** of Defense Tech,
AI, and Next-Gen Energy — the thesis that these three sectors are a single tri-directional
feedback loop (AI needs power; energy needs intelligence; defense funds and consumes both).
The three desks (Defense / AI / Energy) are *feeders*; the **cross-domain convergence brief
is the flagship** (reaffirms D055 Q4). The bilateral and trilateral intersections are
first-class: Defense∩AI (autonomy, counter-UAS, ATR, cognitive EW), Defense∩Energy (directed
energy, tactical microgrids, FOB nuclear), AI∩Energy (SMRs, HALEU, interconnection queues,
grid optimization), and the trilateral core (edge-compute power paradox, grid defense, AI
materials discovery). The named **chokepoints** — semiconductors, HALEU/uranium, rare earths,
SMRs, interconnection queues, edge/neuromorphic silicon, DEW/counter-UAS — are the tracked
spine.

**Why:** The convergence is where cutting-edge capital and capability actually concentrate,
and — critically — it is **sourceable with the free-first public-domain stack** (USAspending/
SAM for DEW/counter-UAS/autonomy, already in D059 keywords; EIA/NRC for nuclear/uranium/SMR;
LBNL/ISO for interconnection queues; SEC EDGAR for hyperscaler capex + SMR developers +
defense primes + Form 4/13F; BIS Entity List for export-control chokepoints). **The moat is
not the thesis** — a generic LLM generates the convergence narrative in seconds — **it is the
cited, primary-source evidence layer and entity graph underneath it.** Confident hype figures
("$500B Stargate", "$90B DoD AI") are treated as claims to *source and cite or reject* via the
faithfulness eval, not facts to assert. Operational consequences (priority order): (1)
convergence requires ≥2 desks of live data, so **breadth now beats Defense depth** — SEC EDGAR
is the next adapter precisely because one source spans all three desks + smart-money; (2) add
a **cross-sector materiality boost** (items touching 2+ desks score higher — the convergence
signal is the valuable signal); (3) the convergence brief is the headline product, desks feed
it. Builds on D055 §5 (moat = entity graph + cross-domain edges) and the finance-forward
source priority (D055 §10). Origin: operator's tri-sector ontology, 2026-06-14.

---

## D061 — SEC EDGAR adapter v1: full-text search, cross-desk probes *(added 2026-06-14)*

**Decision:** The first EDGAR adapter (`engine/adapters/edgar.py`) uses EDGAR's full-text
search (EFTS, `efts.sec.gov/LATEST/search-index`) over **8-K** material-event filings, driven
by a curated set of **convergence-themed query probes**, each tagged with the desk(s) it
serves. A filing matching a multi-desk probe (e.g. "rare earth" → defense+ai+energy) is
tagged with all of them — that multi-desk tag is the convergence signal (D060). It's the
first cross-desk source: one adapter feeds Defense, AI, and Energy at once. Requires a
descriptive `User-Agent` header (SEC policy), supplied via an adapter `headers` attribute now
passed through by the runner. Probes are walked via the runner's page counter (page → probe
index); a stateful `_active_probe` carries the desk tags from `build_request_payload` into
`parse` (calls are sequential per run).

**Deferred to follow-on EDGAR adapters** (different response shapes / prerequisites):
company-facts/XBRL **capex** (per-CIK — wants the entity graph seeded with CIKs first; it's
the AI∩Energy demand-engine signal), **Form 4 / 13F** ownership (filing-document XML parsing —
the smart-money layer, D055 §10), full-text **body** extraction (v1 cites filing *metadata*,
which is honest for a discovery signal: "X filed an 8-K referencing Y on Z"), and per-probe
**sub-pagination** (8-K daily volume per convergence phrase is low — first page suffices).

**Why:** EDGAR is the highest-leverage single source under D060 — it spans all three desks
plus smart-money. EFTS is the cleanest entry point: one GET endpoint, JSON, date/form/query
filters, returning company + ticker + CIK + accession (which also strengthens the entity
graph, since CIK↔ticker is already in the resolver). The probe-set is the D059 deterministic
pre-filter applied to filings. Validated: 16 unit tests + a live smoke test that returned
NuScale/Graham (SMR), Palladyne AI (autonomous weapon), and Skyworks (rare earth/semis) —
the convergence thesis as citable filings.

---

## D062 — Desk-scoped brief generation (multi-desk) *(added 2026-06-14)*

**Decision:** `generate_brief(desk)` is genuinely desk-scoped. Candidate scoring
(`_score_candidates`) and RAG retrieval (`build_query_vector`, `fetch_passages`) now filter to
records where `desk = ANY(nr.desk)`, and the synthesis prompt uses a **desk-aware analyst
persona** (defense-technology / artificial-intelligence / energy-technology) instead of a
hardcoded "Defense" one. The `= ANY(desk)` membership test deliberately **includes multi-desk
records** in every relevant desk's brief — so an EDGAR "rare earth" filing tagged
`defense+ai+energy` surfaces in all three desk briefs and, thanks to the cross-sector boost
(D060), ranks near the top of each. `daily-brief.yml` now offers all three desks.

**Why:** Until now `generate_brief` filtered nothing by desk — it scored every record in the
window and only changed the LLM's framing, which was invisible while only Defense (USAspending)
flowed. With EDGAR feeding all three desks (D061), an unfiltered AI or Energy brief would have
pulled defense awards too. Desk membership (not equality) is the right test because convergence
records legitimately belong to multiple desks; that overlap is the feature, not a bug. This
unblocks the AI and Energy desk briefs and is the substrate for the eventual flagship
convergence brief (D060). Validated: 166 tests pass (desk-aware-prompt unit tests added; the
desk-filter SQL is exercised by the live multi-desk brief run).

---

## D063 — A brief is capital-flow + advancement synthesis, not a contract ledger *(added 2026-06-15)*

**Decision:** A desk brief is a **synthesis of where capital is flowing and forming, and where
technology is advancing** — across **public *and* private** signals — surfacing areas an
investor may find worth their capital or their next hour of research. It is **not** a list of
government contract awards. Every item is framed as a **cited investment-relevant signal**
("capital is concentrating in X; here's why it's notable and what to watch"), never a buy/sell
recommendation (stays on the informational side of the product's disclaimer). Sharpens D060.

**Why:** The vision is an analyst surfacing concentration of capital and capability, not a
data dump — which is exactly the convergence moat (synthesis + provenance). This has three
consequences: (1) **Source breadth** must span the full capital-formation + advancement
picture, not just government procurement: gov capital (USAspending), public + smart-money
(EDGAR / Form 4 / 13F), **private** capital (SEC Form D + news), **technology advancement**
(arXiv, Epoch AI, USPTO patents, Hugging Face), and macro/geopolitics (FRED, GDELT, BIS). The
current stack skews government + public-company; private capital is a known free-data gap
(Crunchbase/PitchBook are paid; Form D is the free proxy), and advancement sources aren't wired
yet. (2) **Synthesis framing** evolves from "prioritize high-dollar awards/filings" toward
"investment-relevant signal." (3) **Guardrail:** synthesis surfaces + contextualizes signals
with provenance; it must not tip into recommendations (informational research, not advice).
This reframes the source-onboarding priority (D055 §10 / per the 2026-06-15 source review):
re-route USAspending to AI/Energy first (cheapest, daily, structured), then Epoch AI + Ember +
arXiv + Form D; keep GDELT as the news/radar layer (D055), not a min-items filler.

---

## D064 — USAspending re-routed to all three desks (multi-desk probes, per award type) *(added 2026-06-15)*

**Decision:** USAspending is no longer pigeonholed to Defense. It now runs **five thematic
probes** (the EDGAR probe model, D061), each tagging records to the desk(s) it serves with
DISJOINT keyword sets (so desk tags are deterministic under content-hash dedup): pure
defense-tech → Defense; autonomy/AI-for-defense → Defense∩AI; AI compute → AI; energy
transformation → Energy; rare-earth/critical-minerals → Defense∩AI∩Energy. Multi-desk probes
are the convergence signal (cross-sector boost, D060). Each probe carries its **own award-type
group**: Defense probes query procurement **contracts** (A–D); AI/Energy/convergence probes
query **grants/financial assistance** (02–05). Lookback widened to 14 days.

**Why:** Per D063, USAspending is the cheapest unblock for the starved AI/Energy desks —
government capital formation, daily, structured, free. Two things had to be right, both found
by smoke-testing against the live API (cf. PAT-CLOUDGAP): (1) **award-type segregation** —
`spending_by_award` can't mix contract and assistance types in one query, and AI/Energy
capital formation (DOE/NSF/ARPA-E research + buildout) flows as *grants*, not procurement
contracts; querying contracts for AI returned generic gov-IT noise (Peraton/Accenture for Dept
of Education), while grants returned the real research/buildout money (DOE, SETI, universities).
(2) **probe-index vs API-pagination** — the runner's `page` counter selects the probe, but it
was also being passed as the API's `page` field, so probe 4 requested result-page 4 (offset
300) and returned empty; fixed by pinning API `page=1` (one page per probe; EDGAR already did
this with `from=0`). After both fixes, all five probes return data live (defense 100, def∩ai
55, ai 7, energy 28, convergence 1) — AI and Energy unblocked. A common field set valid for
both award groups keeps one request shape. Future refinement: AI-grant keywords also catch HHS
biomedical-HPC grants (tangential); Epoch AI (D063) will give cleaner AI-infrastructure signal.

---

## D065 — Space is a Defense∩AI convergence probe, not defense-only *(added 2026-06-15)*

**Decision:** USAspending's space keywords (satellite, spacecraft, launch vehicle, space launch,
geospatial, satellite communications, space-based) are split into their own probe tagged
**Defense∩AI**, separate from the kinetic/sensing defense probe (directed energy, missiles,
radar, EW, drones → Defense only). Civil-space awards (incl. NASA) are **kept and tagged to both
desks**, not excluded. This grows USAspending to six probes.

**Why:** The first live multi-desk run surfaced an all-NASA Defense brief (Northrop/SpaceX/
Honeybee/Astrobotic — civil space), which looked like mis-scoping. The considered fix was to
exclude NASA from Defense. The operator overruled that: space is a defense capability (ISR,
launch, resilient comms) **and** AI infrastructure (space-based data centers, satellite-internet
connectivity), so civil/military space belongs in *both* desks rather than being filtered out.
Tagging space Defense∩AI (a) keeps the high-dollar space awards that were already flowing, (b)
routes them into the starved AI desk, and (c) earns them the cross-sector materiality boost
(D060) as a genuine convergence signal. Kinetic/sensing defense (missiles, radar, EW) stays
Defense-only because it isn't inherently AI. Keyword sets remain disjoint so desk tags stay
deterministic under content-hash dedup. Validated: 198 tests pass.

---

## D066 — arXiv adapter: the technology-advancement leg of a brief *(added 2026-06-15)*

**Decision:** Add an arXiv adapter (`ArxivAdapter`, source_id `arxiv`) as the first **advancement**
source per D063 — capability signal, not capital flow. Five probes: three pure-AI (frontier/
scaling, AI systems/compute, quantum/chips), one Defense∩AI (autonomy/robotics, cs.RO), one
AI∩Energy (grid/fusion ML). It is the AI desk's depth source — the desk USAspending+EDGAR leave
starved (the live AI brief mustered only 3 thin items). Two design points: (1) arXiv returns
**Atom XML, not JSON**, so the adapter declares `response_format = "text"` and `parse()` takes the
raw XML body; the fetcher and runner thread the format through (default `"json"`, back-compatible
with every existing adapter). (2) Papers have **no `amount_usd`**, so the content hash is over
intrinsic fields (id/version/title/abstract), excluding the probe theme so cross-probe matches
dedup to one row. source_weight = 0.7.

**Why:** Per D063 a brief is capital flow **and** advancement; every wired source so far is
capital flow. arXiv is the cheapest, free, daily advancement feed and the most direct unblock for
the AI desk. The materiality math confirms research surfaces without a dollar amount: novelty
(0.30) + authority (0.7·0.25 ≈ 0.175) clears the 0.35 threshold on its own, so papers appear but
rank below billion-dollar awards — correct, since a preprint is a *signal to watch*, not a capital
event. arXiv abstracts are substantive (unlike EDGAR's thin metadata, D067), so synthesis can
ground a faithful claim and items survive citation-eval. A `source_registry` migration
(`20260615000001_add_arxiv_source.sql`) registers the source; operator must apply it + run ingest
before arxiv appears in briefs. Validated: 198 tests pass (new `test_arxiv_adapter.py` + fetcher
text-mode test). Author mentions are typed `person` (materiality importance), the one adapter that
sets `entity_type` — a cross-adapter entity-typing pass is deferred.

---

## D067 — EDGAR full-text items are too thin to survive eval (finding; body extraction deferred)

**Decision (finding):** EDGAR EFTS records, as currently parsed (filing *metadata* only — company,
form, date, theme), are **excluded at citation-eval** because the chunk carries no substance a
claim can be grounded in. In the first live Energy brief both EDGAR 8-Ks (USA Rare Earth, Skyworks)
were dropped (faithfulness 0/1). EDGAR therefore contributes ingested rows but ~0 *published*
value today. Defer a follow-on enrichment: fetch the actual filing body (the 8-K item text / press
exhibit) so the chunk has groundable content, per the v1-scope deferral already noted in
`edgar.py`. Also revisit EFTS reliability (repeated 500s on ingest, recovered by retry).

**Why:** Recording this so the gap is explicit and tracked rather than rediscovered. EDGAR's value
proposition (D061) is public + smart-money capital signal across all three desks; that only lands
once filings carry text, not just headers. Lower priority than the AI-desk unblock (D066) because
USAspending already carries Defense/Energy and EDGAR's convergence probes overlap arXiv's; promote
when private/public-company capital depth becomes the binding constraint (cf. D063 source breadth).

---

## D068 — Brief citation pool is aligned to the material facts (multi-source unblock) *(added 2026-06-15)*

**Decision:** The brief generator no longer derives its citable passages from RAG similarity
alone. `generate_brief` now: (1) scores materiality **first**; (2) selects the fact set with
`_select_facts` — top by materiality but reserving up to `brief_advancement_floor` (default 3)
slots for advancement records (`research_paper`) so capital flow can't crowd out the technology
leg (D063); (3) builds a **citable passage for every selected fact** (`_candidate_passages`) and
**unions** it with RAG context passages (`_merge_passages`, dedup by raw_record_id, fact passages
win, re-indexed 1..N); (4) seeds the RAG query vector from the **material facts**, not the most
recent records. Invariant: every verified fact the synthesis is asked to prioritize has a passage
to cite.

**Why:** The first live multi-source AI brief (USAspending + EDGAR + 190 arXiv) **failed** — 5 of
6 items excluded, only the arXiv item surviving. Root cause found by dogfooding: the citation pool
(RAG, similarity-ranked) and the verified facts (materiality, $-ranked) were computed
independently. `build_query_vector` seeded the query from the 5 most *recent* records, so the
fresh 190-paper arXiv ingest hijacked retrieval — the top-20 citable passages came back all-arXiv,
while materiality still handed synthesis the high-$ awards. The model wrote SAIC/Honeybee items it
could only cite to arXiv passages, and citation-eval correctly failed them (`passing=0`). It had
worked pre-arXiv only because each desk was effectively single-source, so facts and passages
coincided by accident; the first high-volume mixed source broke that. Aligning the citation pool
to the facts (and seeding retrieval by materiality) makes mixed-source briefs publishable, and the
advancement floor keeps arXiv represented rather than crowded out by high-$ capital. This — not
more adapters — was the binding constraint; adding Epoch/Ember first would have worsened the
dilution. Validated: 209 tests pass (11 new alignment tests + helper-level checks); live re-run of
the AI brief is the operator confirmation. Fact passages don't require embeddings, so material
records are citable even before the embed step completes. Follow-up: the materiality formula still
caps no-$ records (arXiv) at ~0.58 — a research-novelty weighting could let advancement compete on
merit rather than via a reserved floor.

---

## D069 — Briefs publish only individually-supported sentences; gate on provable items *(added 2026-06-15)*

**Decision:** Citation faithfulness is now enforced at the **sentence** level, not by an aggregate
threshold. `eval_item` returns a `cleaned_body` containing only the cited sentences the evaluator
LLM marks supported; `run_brief` publishes that cleaned body (re-deriving citation_indices) and a
brief **passes when it has ≥ `brief_min_items` provable items**, dropping the old
`faithfulness_score ≥ 0.95` gate. A partially over-claimed item is **trimmed** to its provable
sentences instead of dragging the whole brief below threshold. Separately, `persist_brief` is
wrapped in a new `db.transient_retry` decorator so a transient DNS/connection blip on the
post-synthesis write can't discard an already-generated brief.

**Why:** Live runs exposed that brief generation is **not reproducible** despite `temperature=0`
(deepseek/OpenRouter don't honor it): the Energy desk **failed at 0.947 then passed at 1.000 on
identical data**, and the same EDGAR 8-Ks that passed in the AI/Defense briefs were excluded
minutes later in Energy. Gating a publish on an aggregate score that itself flips run-to-run made
autonomous publishing (the operator's stated goal) a coin flip. Sentence-level cleaning makes
faithfulness a *construction guarantee* — every published sentence is verified — so the gate can be
the honest, stable question "are there enough provable items?". This is the natural extension of
D058 (strip *uncited* sentences) to *unsupported-but-cited* sentences; the per-item pre-clean score
is still logged as an over-claim signal. The DNS wrap addresses a real crash seen this session:
Energy's synthesis ran ~4 minutes, by which point the pooler had dropped the idle connection and
`persist_brief`'s re-acquire hit `getaddrinfo failed` and aborted a good brief (`create_pool`'s
retry only covers pool creation, D057). Validated: 215 tests pass (6 new — cleaned_body trimming +
transient_retry). Trade-off: dropping the 0.95 aggregate gate means the stored faithfulness_score
is no longer the publish gate; it's retained as a quality metric. Follow-up still open from D068
(research-novelty materiality weighting) and D067 (EDGAR body extraction).

---

## D070 — Publish gate counts provable claims, not items *(added 2026-06-16)*

**Decision:** A brief publishes when it has `>= brief_min_claims` (default 3) **provable claims**
— the sum of LLM-supported claims across surviving items (`CitationEvaluator.provable_claim_count`)
— replacing the `surviving_items >= brief_min_items` gate in `run_brief`. `brief_min_items` is
kept, but only for its other role: the minimum *material candidates* required to attempt a brief
(the `generate_brief` guard).

**Why:** D069 removed the faithfulness coin-flip, but the live re-runs showed the fragility had
just moved to item *count*. The synthesis (deepseek, non-deterministic even at temperature 0)
packs the same facts into **few dense items or many thin ones** run-to-run: Energy published as 2
items carrying 9 claims, Defense as 8 items of 1 claim each. Gating on item count left Energy
sitting right at the minimum — a heavier-consolidation run could publish 1 item of 9 claims and
*fail* an item-count gate despite being substantive. Counting claims is invariant to how synthesis
distributes facts across items, so the gate measures substance, not packaging, and an autonomous
run won't flake on the consolidation lottery. Claims are already verified (D069), so this counts
only provable content. Validated: 220 tests pass (5 new). Minor residual risk: many claims about a
single record could inflate the count; distinct-cited-records would be even more robust and is a
possible future refinement. This was the last fragility before enabling autonomous daily publishing.

---

## D071 — Layered brief: gated facts + grounded analysis layer (two-tier eval) *(added 2026-06-16)*

**Decision:** A brief evolves from a cited fact ledger into a **layered** document. Each signal
carries: a `fact` (cited prose, gated per-sentence exactly as D069/D070), a `read` (analysis — why
it's material, second-order effects, who's exposed), and an optional `watch` (forward catalyst /
confirming-or-disconfirming signal); the brief carries a `convergence_read` tying signals across
desks into the Defense∩AI∩Energy thesis (D060). The analysis layer is **interpretation, not cited
claim**: it is NOT held to per-sentence citation, but it is held to a new guardrail —
`CitationEvaluator.eval_analysis` — that flags any **new concrete fact** (number, dollar amount,
named entity, date, specific event) absent from the cited fact set. Interpretation, implication,
comparison, and forward framing are allowed; fabrication is not. The disclaimer ("not investment
advice") covers the analysis layer; framing stays decisioning-lens, never "buy/sell" (D063).

**Why:** The strict citation gate (D069) that earns trust also forces *descriptive* prose — every
sentence must trace to one source, so interpretive sentences get stripped, leaving "X filed an 8-K"
ledgers. That's a Google Alert, not something anyone subscribes to; the moat is synthesis +
provenance and we had only provenance. Operator chose (a) the layered shape and (b) prototyping
depth before billing — depth is the value driver, so build the thing worth paying for first. The
resolution is to stop holding analysis to the fact-gate and instead hold it to a *different* bar
(grounding, not citation), which is what makes analytical depth coexist with the trust model.

Built in phases: **P1a (this commit)** — the `eval_analysis` grounding guardrail + `AnalysisEvalResult`,
tested in isolation (224 tests pass) since it's the riskiest, most reusable piece; nothing calls it
yet. **P1b** synthesis prompt + generator emit the layered fields; **P1c** run_brief runs the
two-tier eval and prints the layered brief to validate quality on one desk before **P2** persistence
(migration: `read`/`watch` on items, `convergence_read` on briefs) and **P3** BriefReader drill-down
UI. Validated at the print level before schema/UI so the eval-rework risk is retired cheaply.

**Calibration (analyst voice, after the first live P1 run):** the first prototype run showed the
guardrail mis-tuned — it flagged *legitimate* analytical context (real DoD programs like Replicator/
JADC2, end-uses like "rare earths in radar/EW") as fabrication, which is the analytical value, not
a violation. Per operator, the analysis layer uses an **analyst voice**: `eval_analysis` now flags
ONLY *fabricated specifics about the cited subjects* (a wrong/invented amount, date, or quantity; or
asserting as definite a contract/award/event the facts don't support); general domain knowledge,
naming real programs/agencies/end-uses as context, and hedged speculation are allowed. Residual risk
is carried by an "Analysis — HPI interpretation" label (P3 UI) + the not-advice disclaimer (D063).
The same run also exposed that analysis must be grounded against the **rich** fact set (item
headlines + source-passage excerpts), not just the citation-trimmed body — D069 trimming can strip a
subject (e.g. the awardee/amount) from the body, which would otherwise read as a fabrication.
Separately noted: that trimming can leave a semantically thin published fact (an award's period
without its subject) — a D069 refinement to revisit.

## D072 — Regenerate-on-failure publish gate *(added 2026-06-16)*

**Decision:** Brief generation is wrapped in a small retry loop, `generate_publishable_brief`
(`engine/brief/publish.py`): generate → evaluate, return the first attempt that clears
`brief_min_claims` (D070), else regenerate up to `brief_max_attempts` (default 3) and persist the
**best** attempt seen (most provable claims), marked failed. The publish-gate logic that lived in
the untested `scripts/run_brief.py` was extracted here (`evaluate_brief` + the `BriefAttempt`
dataclass) so it is unit-tested; `run_brief.py` now just calls the wrapper and prints.

**Why:** Two live `--desk defense` runs twelve minutes apart on identical data diverged at the gate
— one published with 5 provable claims, the next *failed* with 2 (5 of 6 items excluded by the
citation eval). The synthesis model (deepseek) is non-deterministic even at temperature 0, so D069
(faithfulness) and D070 (item-count) closed the wrong fragility's siblings but left the gate itself
a coin-flip: on an unlucky draw a scheduled desk silently goes dark. Empirically a re-run usually
clears it, so regenerating on failure converts the coin-flip into reliable autonomous publishing.
Only failing desks pay the extra synthesis cost (~$ per attempt); a passing desk returns on attempt
1. This is the last reliability gap before trustworthy cron publishing (P2 persistence / P3 UI next).

## D073 — Persist the layered analysis layer behind a grounding gate *(added 2026-06-16)*

**Decision:** The analysis layer (per-item `read`/`watch`, brief-level `convergence_read`) is now
persisted (migration `20260616000001`: `read`/`watch` on `brief_items`, `convergence_read` on
`briefs`, all `NOT NULL DEFAULT ''`) so it can be rendered (P3). Before persistence every analysis
field passes a **regenerate-then-omit** grounding gate (`engine/brief/analysis.py:ground_brief_analysis`):
if `eval_analysis` (D071 analyst voice) flags a field for fabricating a specific, rewrite it once
(`analysis_max_regen`=1) to strip the fabrication while keeping the analyst voice, re-check, and if
it still doesn't ground, store `""`. So a persisted/rendered analysis field is **always grounded** —
an empty field means analysis was withheld, never that a fabrication reached the reader.

**Why:** P1 validated the layered *form* and the analyst-voice eval, but two live runs showed the
synthesis reliably re-invents the same checkable specific (a "CARLA-VR integration" not in the cited
paper). The eval catches it every time, so the missing piece before rendering is a gate that *acts*
on the flag. Operator chose regenerate-then-omit (over omit-immediately or persist-with-a-flag): it
preserves an otherwise-good read by stripping just the bad specific, and only spends an extra LLM
call when a field is actually flagged — mirroring D069 (trim facts to the provable) and D072
(regenerate the brief on a bad draw). This is the trust model extended to analysis: never publish
unprovable content, whether it's a fact (citation gate) or an interpretation (grounding gate).

Scope: P2a (this commit) is persistence + the grounding gate, unit-tested with eval/LLM mocked
(240 tests). **P2b** batches the per-field eval into one call (today it's ~one eval per field, plus a
regen call per flag) — a pure optimization, deferred. **P3** renders `read`/`watch`/`convergence_read`
in BriefReader behind an "Analysis — HPI interpretation" label (D071 residual-risk control).

**Hardening (generation exceptions, added 2026-06-16):** `generate_publishable_brief` now treats a
generation/eval *exception* as a failed attempt and retries within the same budget, not just a
failed claim-count gate. Motivation: a live run showed deepseek occasionally returns a
whitespace-only, non-JSON body; litellm's configured fallback usually recovers, but if both primary
and fallback fail the call raises (litellm `APIError`, or the `RuntimeError` from invalid JSON) —
which `run_brief` only caught as `RuntimeError`, so an unattended desk run would crash instead of
regenerating. The loop now catches any attempt exception, logs `brief_attempt_failed`, and retries;
if some attempt produced a (sub-floor) brief it returns the best, and only if EVERY attempt raised
does it re-raise as `RuntimeError` (chaining the cause) so the caller's failure path still fires.

## D074 — Novelty / anti-rehash gate *(added 2026-06-16)*

**Decision:** Before fact selection, `generate_brief` down-ranks any candidate record whose
`(source_id, native_id)` was already cited in a **published** brief for that desk within the last
`novelty_window_days` (default 7), by multiplying its materiality score by `novelty_penalty`
(default 0.5) and re-sorting (`apply_novelty_penalty` + `_recently_featured` in
`engine/brief/generator.py`). It demotes, it does not drop: a long-lived item can still re-lead when
nothing fresher is material, so the brief is never forced empty by the gate.

**Why:** The daily window already scopes to records ingested since the last publish (`_get_window_start`),
but long-lived records re-surface — the $22.4B Boeing/NASA award led the defense brief on multiple
consecutive days because it keeps re-scoring material whenever re-ingested. For a *daily* product
that reads as rehash, which kills credibility. Keying on `native_id` (a stable external id — award
number, 8-K accession) rather than `raw_record_id` means re-ingestion of the same item is still
recognized. Demote-not-drop keeps the existing safety valve intact: if a desk genuinely has nothing
fresh, it still produces its strongest brief rather than failing `brief_min_items` and going dark —
honesty over novelty when forced to choose. Only *published* briefs count as "already covered"; a
failed/superseded brief never reached a reader. Tunable: penalty 1.0 or window 0 disables the gate.

## D075 — Subscription state: Lemon Squeezy webhook persistence + comp grants *(added 2026-06-16)*

**Decision:** The Lemon Squeezy webhook now **persists** subscription state (it was a Gate-6 stub
that only logged), and a comp-grant path lets us grant Pro without payment. Supporting both required
making the `subscriptions` table provider-correct: migration `20260616000002` renames `stripe_*` →
`ls_*`, drops `NOT NULL` on `ls_customer_id`, and adds `source TEXT CHECK (lemonsqueezy|comp)`. The
webhook (`api/app/routers/webhooks.py`) upserts one row per `user_id` (from checkout `custom_data`)
on `subscription_*` events — `tier='pro'`, status mapped from LS (`on_trial→trialing`, `active→active`,
`past_due/unpaid→past_due`, `cancelled/expired/paused→cancelled`), `current_period_end` from
`renews_at`, `source='lemonsqueezy'` — idempotent and signature-verified, degrading to
accept-and-ignore when unconfigured (D045). Comps are a `source='comp'` row (tier pro / status active,
no LS IDs, optional expiry) written by `scripts/grant_comp.py --email`. `resolve_tier` treats paid
and comp identically (`tier='pro' AND status IN ('active','trialing')`).

**Why:** Checkout was wired but the webhook never wrote the row, so a paying user would still
resolve to `free` — the revenue loop was silently broken. The table was also Stripe-named (pre-D050
leftover) and its `stripe_customer_id NOT NULL UNIQUE` made comps impossible. The table was empty
(no subscription ever succeeded), so the rename was zero-data-risk. Comp grants are the marketing
lever (press/VIP access) the operator asked to bake in; keeping them in the same `subscriptions`
surface (distinguished only by `source`) means one tier-resolution path and no parallel system.
The webhook never clobbers a comp because it always writes `source='lemonsqueezy'` on its own rows
and comps are managed out-of-band.

Operator steps to go live: `supabase db push` (apply the migration); create the LS webhook +
`fly secrets set LEMONSQUEEZY_WEBHOOK_SECRET`; then a test-card purchase flips the account to Pro
end-to-end. `grant_comp.py` requires DB access to `auth.users` and the user to have signed up first.


## D076 — LLM call-layer backoff for transient provider failures

**Decision:** `LLMClient` now wraps every `litellm.acompletion` call in delay-and-retry with
exponential backoff + jitter (`engine/llm/client.py`, settings `llm_max_retries=4`,
`llm_backoff_base_seconds=2.0`, `llm_backoff_max_seconds=30.0`). Retryable errors are
`RateLimitError`, `APIError`, `APIConnectionError`, `Timeout`, `ServiceUnavailableError`,
`InternalServerError` (built defensively via `getattr` so a litellm version drop can't break import);
anything else propagates immediately. Both the primary call and the JSON-repair retry route through it.

**Why:** The 2026-06-17 scheduled run sent a false "All jobs failed" email. Root cause from the logs
was NOT data starvation — it was an OpenRouter **429** ("qwen3.7-max temporarily rate-limited upstream")
plus a deepseek non-JSON `APIError`. The three desks run back-to-back and exhaust the free-tier rate
budget, so energy (last) gets refused. A rate-limit is a *time window*; the brief-level re-roll (D072)
retried immediately and landed inside the same blocked window, so it couldn't clear it. Backoff at the
call layer sleeps past the window and self-heals. Paired operator action: add paid OpenRouter credits
(removes the free-tier upstream limit entirely); backoff covers transient blips regardless. Jitter
de-syncs concurrent desk calls. This is reliability for unattended daily publishing, not a quality change.

**Honest run reporting (same gate):** `scripts/run_brief.py` now exits with a code the daily
workflow reads — `0` published, `3` generated-but-below-the-claim-floor (a clean "thin desk" skip,
not an error), other = hard crash (a `RuntimeError` after backoff = real outage). `.github/workflows/
daily-brief.yml` captures each desk's code, writes a `published / skipped / crashed` summary to
`$GITHUB_STEP_SUMMARY`, spaces desks 15s apart to ease the rate budget, and exits non-zero (→ the
"run failed" email) ONLY when a desk crashes or nothing published. A sparse desk skipping on a slow
news day is now a normal green run, not a false "All jobs failed" alarm — the signal operators (and
soon testers) watch is trustworthy.


## D077 — Widen the EDGAR probe set (desk depth)

**Decision:** Expanded the EDGAR full-text probe set from 8 to 40 convergence-themed phrase
queries (`engine/adapters/edgar.py`), keeping the original 8 at their pinned page positions and
appending depth per desk: Energy (grid-scale storage, PPAs, LNG, uranium enrichment, geothermal,
microgrid, …), Defense (munitions production, missile defense, loitering munition, shipbuilding,
Defense Production Act, …), AI/compute (large language model, GPU, semiconductor fabrication,
advanced packaging, liquid cooling, …), and trilateral chokepoints (rare-earth magnet, gallium,
germanium, critical minerals, quantum). The adapter now exposes `max_pages = probe_count`, and
`engine/ingest/runner.py` reads an adapter-declared `max_pages` (explicit caller arg > adapter cap >
global `ingest_max_pages`) so the global safety cap of 10 no longer silently truncates the probe walk.

**Why:** The 06-17 energy miss exposed that a single sparse desk can fall below the 3-provable-claim
floor on a slow window — and the EDGAR net was only 8 phrases over 8-K metadata, so energy's entire
input was a handful of filings. EFTS has no regex/wildcards (only exact phrases + boolean OR), so
breadth comes from more probes; one phrase per probe preserves clean theme + desk attribution (D059)
and is trivially editable by the operator (the probe list IS the convergence-thesis curation, the
moat). More fact-dense filings per desk per day → more candidate facts → a reliable claim floor.
This is the query-breadth half; D078 (filing bodies) adds extraction depth per filing.


## D078 — EDGAR filing-body extraction (fact density)

**Decision:** Added a best-effort body-enrichment pass to the EDGAR adapter
(`engine/adapters/edgar_body.py` + `EDGARFullTextAdapter.enrich`). After `parse`, the runner
calls an optional `adapter.enrich(records, fetcher)` hook; EDGAR fetches each hit's actual filing
document, strips HTML with the stdlib `html.parser` (no new dependency), and mines it with regex for
dollar amounts (normalized to USD, incl. "$1.5 billion" / "$3.2B"), percentages, and dates. It sets
`structured_data['amount_usd']` to the largest figure, stores `body_amounts_usd` / `body_dates`, and
rebuilds `text_chunk` as metadata + a compact key-figures line + a body excerpt centred on the first
dollar amount. Bounded by `edgar_max_bodies_per_run=80` with a 0.15s inter-fetch courtesy delay; any
fetch/parse failure logs `edgar_body_failed` and keeps the metadata record (never drops a record).

**Why:** The publish gate counts *provable claims* — sentences whose cited source contains a checkable
fact — and EFTS metadata ("Acme filed an 8-K") carries no numbers, so it can't produce them. The body
is where the dates and dollar figures live. The biggest structural win is `amount_usd`: the materiality
scorer (D035) magnitude-normalizes that field, which EFTS records never populated, so body-extracted
contract/award figures now actually drive materiality, not just synthesis. This is the local-side regex
extraction the operator asked for — robust pattern matching applied to filing text after fetch, which
EFTS's phrase-only query layer cannot do. Pairs with D077 (more probes = more filings; D078 = more
facts per filing). Future: enrich only post-dedup to avoid re-fetching unchanged filings.


## D079 — Ingest resilience: a transient single-source outage must not abort the daily job

**Decision:** `scripts/run_ingest.py` now exits non-zero only on a *total* ingest failure (every
source failed), via a tested `decide_exit_code(statuses)` helper, and prints an "Ingest summary:
N ok, N skipped, N failed" line. Previously any single source with `status='failed'` set exit 1.

**Why:** The 06-17 13:44 manual energy validation run failed in 27s — not on the brief, but on the
*ingest* step: SEC EFTS returned repeated HTTP 500s (external/transient — it had worked 3 hours
earlier, and the failure hit page 1 / an original probe, so not the D077 widening). The fetcher
retried and gave up, `run_ingest.py` exited 1, and under the workflow's `bash -e` that aborted the
whole job *before any brief ran* — even though arxiv + usaspending ingested fine and briefs could
publish from existing DB data. This is the Gate-2 (D076) honest-failure principle applied to the
ingest layer: a flaky upstream source should degrade input freshness, not take the product dark. Now
EDGAR can 500 and the job still proceeds to publish; only a systemic failure (e.g. DB unreachable,
all sources down) exits non-zero. The D077/D078 depth improvements still need EFTS up to be exercised
on fresh data — re-validate on a run when SEC is healthy.


## D080 — /account page (tier + Pro badge + manage-subscription link)

**Decision:** Added the `/account` page (`web/app/account/page.tsx`, a server component) so a
subscriber can see and manage their plan. It reads the existing `/auth/me`, which now also returns
`source` ('lemonsqueezy' | 'comp' | null) and `customer_portal_url`. Rendering by state: **Free** →
FREE badge + "Upgrade to Pro" → /subscribe + benefits list; **Pro (paid)** → PRO badge, member-since,
renews-on, and a "Manage subscription" button → the Lemon Squeezy customer portal; **Pro (comp)** →
"PRO · COMPLIMENTARY" badge + a note that there's no billing to manage. To supply the portal link,
migration `20260617000001` adds `subscriptions.customer_portal_url`, and the webhook now stores
`data.attributes.urls.customer_portal` (COALESCE-preserved across events that omit it). The navbar
already linked `/account`; the page just didn't exist (404 until now).

**Why:** Field testing needs the tester experience complete — a Pro user had nowhere to see "Pro" or
cancel. Comp grants (the field-test mechanism, D075) are explicitly handled: a comp has no LS billing,
so the page says so rather than dangling a dead "manage" link. The page **degrades gracefully** if the
API isn't redeployed yet (`source`/`customer_portal_url` come back undefined → it shows a "manage via
your Lemon Squeezy receipt email" note), so the Vercel deploy of the page is safe ahead of the API.
Deploy ORDER matters: `supabase db push` (add the column) BEFORE `fly deploy` the API (which SELECTs
it). Known limitation: the stored portal URL is a signed link that LS rotates (~24h); it's refreshed on
each subscription_* event. Hardening (post-launch): fetch it fresh from the LS API on demand.


## D081 — SEC Form D ingestion (private-capital-formation signal)

**Decision:** The EDGAR adapter now queries `forms=8-K,D` (was `8-K`), so the convergence
probes also surface **Form D** Reg D private-placement filings. `enrich()` routes by form type:
an 8-K is mined from its HTML body (D078); a Form D is mined from its structured
`primary_doc.xml` (`_form_d_xml_url`) for `totalOfferingAmount` / `totalAmountSold` / industry
(`engine/adapters/edgar_body.py: extract_form_d_facts`). The offering size populates
`structured_data['amount_usd']` (so the materiality scorer magnitude-ranks it) and `text_chunk`
becomes a citable line: "SEC Form D private placement by <co>: offering $X; $Y sold; industry Z."

**Why:** First "obvious win" toward thicker output — it reuses the existing EDGAR auth/dedup/
entity/enrich plumbing yet opens an entirely new **citable** signal class: private companies
raising capital in AI-infra / defense / energy (the Crunchbase/PitchBook signal, free via SEC).
Offering amounts are exactly the fact-dense, numeric specifics the provable-claim gate rewards.
**Known v1 limitation:** Form D has little free text, so EFTS theme-phrase recall is low-but-high-
precision — we catch placements whose issuer name / clarification matches a probe, and miss others.
v2 (deferred): an industry-filtered Form D pull (Reg D industryGroupType → desk) for fuller recall,
rather than relying on full-text phrase matching. Distinct from the GDELT "Signal" color work
(next): Form D adds *cited facts*; GDELT will add *labeled, attributed aggregate context* (D082).


## D082 — GDELT media-attention "Signal" (complementary aggregate color)

**Decision:** Briefs now carry an optional **Signal** line — labeled GDELT media-attention
momentum (e.g. "SMRs +100%; gallium +40%") — rendered as a disclaimed, dashed block in the
reader, separate from the fact and analysis layers. Engine: `engine/signal/gdelt.py` computes
per-theme momentum (recent-window mean vs trailing baseline) from the keyless GDELT DOC 2.0
`timelinevol` API; `compute_brief_signal(themes, fetcher)` caps the theme count and builds one
line; `run_brief.py` computes it (best-effort, via `HttpFetcher`) from the desk's probe themes
(`edgar.themes_for_desk`) and attaches `brief.signal`. Persisted to `briefs.signal` (migration
`20260617000002`), serialized by `/v1/briefs`, rendered by `BriefReader`.

**Why:** Correcting an earlier overstatement — GDELT's *own* aggregate volume/tone data is
openly licensed; only the third-party article text it indexes is off-limits. So GDELT CAN add
narrative color, as **labeled, attributed, aggregate momentum** — never a cited fact. The
guardrails ARE the architecture: (1) its own column/render lane, never the provable-claim path;
(2) computed, not LLM-generated, so no fabrication risk and no analysis-grounding-eval change;
(3) explicit "aggregate momentum, not a verified fact" disclaimer in the string itself; (4)
best-effort — any GDELT failure yields "" and the block simply doesn't render, so it can never
fail a brief. Backend is DOC 2.0 now (no GCP); the momentum math + brief-side contract are
backend-agnostic, so a richer **BigQuery GKG** backend (baseline-relative spikes, co-occurrence,
GCAM → `entity_edges`) swaps in later for the convergence-graph moat — only the fetch layer
changes. Complements D081 (Form D = new *cited* facts); together they thicken output from both
the fact and the context sides.


## D084 — Visual/UX Tier 1: at-a-glance ledger + provenance discoverability

**Decision:** First UX pass toward "worth $19.99/mo", grounded in a competitive scan (AlphaSense's
click-to-source, SemiAnalysis's data-first reports, fintech glanceability best practice). Front-end
only, no backend change. (1) **`BriefGlance`** — a scannable "At a glance" ledger above the long read:
per item a type swatch + label, headline that anchor-links to the item, a normalized **magnitude bar**
from the key dollar figure (parsed headline-first via `lib/amounts.ts`, body fallback), and a sources
count; plus a summary strip ("N items · ≈$X tracked · 100% cited"). (2) **Provenance discoverability** —
a visible "Sources (N)" control per item (the `CitationsDrawer` source cards already existed but were
only reachable via tiny inline chips), and `source_id` prettified to display names (`lib/sources.ts`).
Full roadmap (Tiers 1–4) written to `FRONTEND_SPEC.md §9`.

**Why:** HPI's two differentiators — provenance (moat) and convergence (identity) — were visually
under-expressed, and the reader had no data layer or scannable summary (the #1 dashboard failure mode is
prose overload). The at-a-glance delivers the day in ~10 seconds (importance-first); the bars answer
"compared to what?"; surfacing sources turns the citation moat from invisible into a felt feature. NOTE
the dependency: the at-a-glance is brutally honest — a filler item (no $, no event) shows an empty row —
so significance-filtering (the content gate) should land alongside, or the UI spotlights weak items. The
PDF print export had flattened the interactive citation chips to bare superscripts, which had overstated
the provenance-UX gap; the drawer was already solid and is now merely more discoverable.


## D085 — Strategic-significance gate (drop true-but-trivial items)

**Decision:** After materiality selection and before synthesis, `generate_brief` runs an LLM
**significance triage** (`engine/brief/significance.py: filter_significant`) that scores each
selected candidate 0–1 for strategic significance to the desk thesis and drops those below
`significance_threshold` (0.45). It targets exactly the "not worth $19.99" failures seen on the
live desks: routine commodity procurement (the Defense desk's cellular-service contracts), filings
that disclose no material event (the "filed an 8-K, contents unknown" rare-earth filler), and stale
actions resurfacing. Two safety properties: **fail-open** (a candidate the model didn't score, or a
triage-call failure, keeps everything — a junk filter must never be why a brief fails) and **never
empties the pool** (if all score low, the single best survives and the publish gate, not this gate,
decides whether the thin day publishes or cleanly skips). One extra LLM call per brief (the eval
model), temperature 0. Tunable via `significance_enabled` / `significance_threshold`.

**Why:** Materiality ranks by $/source/novelty but not "so what." The publish gate proves claims are
true and cited, but **true ≠ significant** — so trivially-true items padded the briefs and broke the
premium impression (and the new at-a-glance ledger, D084, made them glaringly visible as empty rows).
This gate is the lever that turns "nice format" into "worth paying for." A desk with no significant
news now skips cleanly (better than filler) — which also surfaces, honestly, which desks need deeper
sources. Intentional consequence: thin desks may skip more often pre-launch; that's the correct
quality trade while iterating, and it points the sourcing roadmap.

**Refinement (2026-06-19, curation Step 1) — substance over vehicle.** A Phase B quality pass on the
live AI desk found the gate let *speculative financial vehicles* through: a $3B quantum **SPAC**, a
shoe-company-turned-AI **shell**, and a **non-binding term sheet** all scored HIGH because the prior
prompt rated "M&A and major financings" as significant without distinguishing operating substance from
deal-vehicle mechanics. Reworked the triage prompt to demote SPAC/de-SPAC/blank-check combinations
(esp. pre-revenue targets), cash-shell recapitalizations/pivots/rebrands, and vehicle-only term sheets
into the LOW band — while explicitly **keeping** a non-binding LOI when the underlying development is
materially strategic and the parties are operating companies (e.g., the Centrus/Oklo HALEU supply LOI).
No logic/threshold change — prompt only. Added a curation eval to make this measurable and durable:
`tests/fixtures/significance_golden.json` (labeled keep/drop cases incl. the non-binding discriminator
pair) + `scripts/eval_significance.py` (operator-run, advisory — LLM judgment varies). First run:
**12/12, froth 7/7 dropped, signal 5/5 kept**, scores cleanly separated (froth 0.05–0.30, signal
0.80–0.95) around the 0.45 threshold. Curation Steps 2 (desk-identity tagging) and 3
(cross-desk de-dup) follow separately.

**Refinement (2026-06-19, curation Step 2) — desk-identity tagging.** Phase B also found the AI desk
diluted by generic energy project finance (a solar+storage farm, a wind acquisition, a PPA landing on
"AI Infrastructure"). Root cause: the EDGAR convergence probes (D060) tag energy-power phrases as *also*
AI on a demand-side rationale ("compute needs power"). Operator chose (over a blunt convergence-boost
dial-back or status-quo) to **tighten the tags to compute-proper**: demoted `grid-scale storage`,
`transmission interconnection`, `power purchase agreement`, `solid-state battery`, and `geothermal` from
`(energy, ai)` → `(energy)`. **Kept** as genuine AI∩Energy convergence: `hyperscale data center`, `liquid
cooling`, `graphics processing unit`, and `small modular reactor` (data-center nuclear). This makes the
AI desk "AI infrastructure proper" while preserving convergence where the cross-desk link is intrinsic,
not merely demand-side. Probe *order* is unchanged (pinned positions intact); only desk tags changed, so
the convergence boost (`materiality_cross_sector_weight` 0.15) and the cross-desk convergence chip (T3.7)
now fire on genuinely cross-sector items. Locked by `test_tangential_energy_probes_are_energy_only`.

## D086 — Analysis grounding is best-effort (never lose a passed brief)

**Decision:** `run_brief.py` now wraps the D073 analysis-grounding step in try/except: if grounding
fails, it clears the (ungrounded) analysis fields and publishes the **cited facts only**, rather than
crashing. The FACT layer is already gated and citable; the read/watch/convergence analysis is
decorative and only shown when grounded — so a grounding outage should degrade to a facts-only brief,
not lose it.

**Why:** Root-caused the stale AI desk — on 2026-06-17 the AI brief generated and **passed eval (6
claims)**, but the grounding step's eval-model calls hit the same 429 storm that killed energy, threw,
and crashed `run_brief` **before persist**, so AI never wrote that day's brief and the page kept showing
the Jun-15 pre-layered brief. D076 backoff now covers those calls, but this hardening closes the
structural gap so an analysis-layer hiccup can never again silently drop an already-publishable brief.
Same best-effort principle as the GDELT signal (D082).

## D087 — UX Tier 2 (frontend): type icons, inline magnitude bars, signal trend styling

**Decision:** The brief reader gains a data/glance layer with no backend change. (1) A consistent
**type icon** per `item_type` (award/filing/policy/macro/signal), centralized in
`web/lib/item-types.ts` (label + color token + icon in one place, killing the duplication across
`brief-glance` and `brief-content`), replacing the bare color dot in both the at-a-glance ledger and
the long read. (2) **Inline magnitude bars** on each item's key dollar figure, normalized to the
brief's largest (reusing the D084 `amounts` parser), so a number reads "compared to what?" right at
the item, not only in the ledger. (3) The GDELT **Signal** line (D082) rendered with a trend arrow +
color per momentum delta (`web/lib/signal.ts` `splitSignal` + `SignalLine`), replacing the flat dashed
text. All presentation-only — the cited facts and the signal's disclaimer text stay authoritative.

**Why:** The competitive scan (FRONTEND_SPEC §9) flagged HPI as prose-heavy with an under-expressed
data layer; Tier 1 (D084) added the at-a-glance ledger, Tier 2 carries that glanceability into the
body and foregrounds the Signal's direction. Kept **frontend-only (no migration)** so it ships on push
and degrades gracefully on older data. The *true numeric sparkline* is deferred to **Tier 2b** because
it needs the GDELT volume series persisted — the `signal` field is currently only a prose string
(`build_signal_line`), so a real sparkline is a schema + generator + API change, not a render change.

## D088 — Honest free-tier onboarding copy + Pro degradation while payments are dark

**Decision:** Two coordinated changes so an invited *free* tester isn't told they must pay. (1)
**Account-creation CTAs reframed** from "Start (14-day free) trial" to free-account language —
"Get the free daily brief" (home hero + navbar), "Create your free account" (`/signup`), "Create a
free account" (login link). Signing up creates a **free account**; the Pro 14-day trial begins on
*upgrade* — so this is more accurate even at launch, and drops the "credit card required" deterrent at
the front door. (2) A server-only **`paymentsConfigured()`** helper (`web/lib/payments.ts`, reads the
`LEMONSQUEEZY_*` env) keys every Pro surface — `PricingTable`, the `/subscribe` hero, `ArchiveLock` —
so they degrade to **"Pro is coming soon - you already get the full daily brief free"** while Lemon
Squeezy is unset, and restore the trial/checkout automatically once the env is set. The checkout route's
503 copy was softened to match ("Pro isn't available yet - you already get the full daily brief free").

**Why:** A tester signed up on mobile and read the post-signup `/subscribe` paywall ("14-day trial,
credit card required"; checkout "not configured") as "I have to pay" - confusing and off-putting for an
account that already sees the full current-day brief on every desk. With the signup->`/desk/defense`
redirect (`ccd393b`) and the mobile-nav hamburger (`92e725b`), this closes the onboarding-confusion
theme before open testing. Degradation is **env-keyed**, so there's no flag to flip at launch - setting
the Vercel env and redeploying flips the marketing surfaces to the trial CTA. Note: those pages are
statically prerendered, so the switch lands on the redeploy that an env change triggers; the checkout
API re-checks server-side at request time, so it's always the authoritative gate.

## D089 — UX Tier 2b: real GDELT signal sparkline (persist the lead-theme series)

**Decision:** Persist the numeric series behind the GDELT Signal so the reader draws a real sparkline,
not just the D087 trend arrow. The GDELT layer already *fetched* the per-theme volume series and threw
it away; now `fetch_theme_signal` keeps it (`ThemeSignal.series`), and `compute_brief_signal` returns a
`BriefSignal` (the labeled prose `line` **plus** the lead theme's series/`delta_pct`/`direction` — lead
= the noteworthy theme with the largest absolute move). `run_brief` stores `BriefSignal.series_json()`
into a new nullable `briefs.signal_series JSONB` (migration `20260618000001`); the API parses it
defensively (asyncpg returns JSONB as a string — no codec registered) and serializes it; the reader
renders a dependency-free inline SVG `<polyline>` sparkline in `SignalLine`, colored by direction.

**Why:** Tier 2a styled the prose; the data layer (FRONTEND_SPEC §9) wanted the curve — "Bloomberg
glanceability." Kept honest and best-effort end to end: `signal_series` is **NULL** when nothing moved
or GDELT was unreachable, it lives beside `signal` and out of the provable-claim path (it's aggregate
attention color, never a cited fact), and the reader degrades to the line-only view (or pre-migration
briefs) with no sparkline. Backward-compatible: the column is additive/nullable and every read guards
on its presence. The richer BigQuery GKG backend can later replace the fetch layer without touching this
brief-side contract.

**Reliability:** the series is written **best-effort, after the brief commits** — a separate `UPDATE`
*outside* the persist transaction (`generator.persist_brief`), wrapped in try/except. So a missing
column (migration not yet applied) or any write error is logged (`signal_series_write_skipped`) and
skipped, never rolling back or darking the already-persisted cited brief. This deliberately removes the
migration-before-deploy hazard for this decorative column: the daily cron runs latest `main`, so putting
`signal_series` in the critical INSERT would have failed the whole brief until `supabase db push` ran —
unacceptable for paid subscribers. OPERATOR: `supabase db push` *enables* the sparkline, but is no
longer a prerequisite for publishing.

## D090 — CI reconciles DB migrations before the daily brief (non-fatal)

**Decision:** `daily-brief.yml` runs `supabase db push --db-url "$DATABASE_URL"` *before* ingest/brief,
so any migration merged to `main` is applied to the remote DB before code that references it runs. The
cron runs latest `main`, so without this, code and schema can desync and dark a brief. The step is
**non-fatal** (`continue-on-error` + warn-and-proceed): the app schema is migration-tolerant (decorative
columns are best-effort, D089), so a reconcile hiccup must never become a *new* way to block publishing.
It reuses `DATABASE_URL` — no project link/login, no new secret.

**Why:** A tester-flagged churn risk — D089's `signal_series` in the critical INSERT would have darked
the brief until the operator manually migrated. The durable answer is two layers of defense: (1) make
decorative schema best-effort so it can't dark a brief (D089), and (2) auto-reconcile *required*
migrations in CI, before any spend on ingest/LLM. Kept non-fatal so the safeguard can't itself fail the
brief. **Caveat:** `db push` takes a session advisory lock the **transaction-mode pooler doesn't
support** — if `DATABASE_URL` is the pooler the step warns instead of applying; remedy is a
direct-connection secret for the reconcile step (DEPLOY_RUNBOOK §6). Verify via the first run's logs.

## D091 — Build the full entity-resolution graph for Tier 3 (not chips-lite)

**Decision:** Build the real entity-resolution graph — seed a reference entity set, a production resolver,
populate `entity_edges`, add entity endpoints, the Entity 360 page, and (last) the convergence
visualization — rather than the LLM-extracted "chips-lite" shortcut. Today none of this substrate exists:
`entities`/`entity_edges` are empty, `brief_items.entity_ids` is hardcoded `[]` (generator.py), and
`resolver.py` is scoring primitives only (no DB-backed resolver, no endpoints, no `/entity` route).

**Alternatives considered:** (a) **chips-lite** — the synthesis LLM already names entities, so emit a
per-item `entities:[{name,ticker?}]`, store in an additive `brief_items.entities` JSONB, render chips +
intra-brief co-occurrence; ~1 gate, no resolution infra, forward-compatible, but tickers are
LLM-asserted/best-effort. (b) **defer Tier 3** until a tester actually asks to click a company.

**Reason for choice:** the entity-resolution graph is the product's stated **moat** (README "transmission
layer"; the Defense∩AI∩Energy convergence north-star). The operator judges that real entity depth is what
makes the product worth $19.99 and separates it from prose-only competitors — worth building deliberately
now rather than shipping a shortcut that gets redone.

**critical-thinker pushback + outcome:** pushed toward **chips-lite-first** (cheaper, validates the want,
forward-compatible, defers the resolution swamp). Operator chose the full graph anyway — accepted as a
deliberate moat investment. **Non-negotiable guardrail carried from the pushback:** the resolver MUST
ship with an **accuracy eval gate** (a golden mention→entity set + a false-link-rate threshold) before
any resolved entity is rendered — a wrong ticker/link directly corrupts the provenance trust model that
is the product's core value, exactly the risk the citation-faithfulness gate exists to prevent. Also
deferred from v1: the d3-style relationship graph (low utility at a few entities/day) — the cross-desk
"convergence" signal ships first as a chip tag ("appears across Defense + AI"). Build sequence (one gate
each): reference set → resolver + eval gate → populate `entity_ids`/`entity_edges` → API → chips →
Entity 360 → (optional) viz.

**Private / venture-backed entities (operator question, 2026-06-18):** the product also cares about
closely-held / pre-IPO firms (Anduril, SpaceX, venture-backed SMR startups) — they move public comps and
signal future listings. The schema already supports them: `entity_type='company'` needs no ticker, and
`entity_identifiers` carries `uei`/`cik`/`duns`/`lei`/`sam_uei`. Population is **two-pronged**: (1) seed
the **public** universe from SEC `company_tickers.json` now (T3.1); (2) **mint private/venture/gov
entities from our own authoritative ingest identifiers** during resolution (T3.2–T3.3) — USAspending
recipient **UEI** (private defense contractors) and EDGAR **Form D** issuers (D081 — venture private
placements) and EDGAR **CIK**. Minting on an *exact* identifier keeps precision high (no fuzzy guess), so
coverage grows organically from what we actually ingest rather than a curated VC list. Private chips
render as name + "private" tag (no ticker).

## D092 — T3.3: wire resolution into briefs (entity_ids), mint private/venture, defer co-occurrence edges

**Decision:** Populate `brief_items.entity_ids` at brief-persist time by resolving each item's source
records, and **mint** private/venture/gov entities from authoritative identifiers — but **defer the
co-occurrence `entity_edges`** that the D091 sequence listed for this gate. The resolver miss that blocked
this (Northrop `/DE/`, recall 0.889→1.000) was fixed first; the eval gate now passes on real seeded data,
so rendering is unblocked.

**How it works:** `engine/entity/linker.py` maps each `normalized_records` row to `(name, identifiers)`
inputs — EDGAR contributes ticker+padded-CIK off the mention, USAspending contributes the recipient UEI
off `structured_data` — then calls the precision-first `resolve_mention`. An item's source records are
reached via its `[CITE:N]` indices → passage `raw_record_id`. Resolution runs on its own connection
**before** the brief transaction and is wrapped in try/except (logs `entity_resolution_skipped`), so an
unseeded graph or any error falls back to empty `entity_ids` and never darks a cited brief — the same
best-effort principle as the signal series (D089) and analysis grounding (D086). Minting only fires when
`resolve_mention` finds no match AND a *mintable* identifier (CIK or UEI — globally unique/authoritative;
a non-seeded ticker is deliberately excluded as suspect) is present, so a private recipient like Anduril
becomes a real entity keyed by UEI and resolves idempotently on later runs.

**Edges deferred — alternatives + reason:** the listed `entity_edges` was *co-occurrence* (two entities in
one item). (a) **co-occurrence now** needs a schema migration — `entity_edges.edge_type` has a fixed CHECK
list with no co-occurrence type — and adds a weak, graph-cluttering signal with no consumer until the (also
deferred) d3 viz. (b) **authoritative semantic edges** (AWARDED/SUPPLIES from the award payload) are far
more valuable and already in the CHECK list, but deserve their own gate. (c) **defer all edges** until a
consumer exists. Chose (c): the only near-term edge consumer is the cross-desk **convergence** chip (T3.7),
which is "the *same* entity_id appears on ≥2 desks" — derivable directly from `entity_ids`, no edges
required. So `entity_ids` delivers chips (T3.5) and convergence (T3.7) with zero edge infrastructure; edges
return as a dedicated gate (semantic, not co-occurrence) when a graph/supply-chain view needs them.

**Verification:** pure input-shaping unit-tested (`tests/unit/test_entity_linker.py`); the DB resolve/mint
path is best-effort and confirmed by the next brief run's `entities_linked` log (items_with_entities count).

## D094 — Frontend test infrastructure: Vitest + Testing Library (jsdom)

**Decision:** Stand up a frontend test runner — **Vitest 4 + @testing-library/react + jsdom** — so web
logic (pure helpers and client-component behavior) can be tested, closing the long-standing gap where only
the backend (`pytest`) had a test suite. First suite covers `lib/amounts.ts`, `lib/entities.ts`, and the
D093 `ReaderOnboarding` localStorage/dismiss behavior (16 tests). `npm test` → `vitest run`.

**Why now:** the reader has accumulated real client-side logic (the D093 onboarding gating, amount parsing
for the D084 magnitude bars, SEC-title casing) that `next build` only typechecks, never *exercises*. A
regression in any of it would ship silently. This is the "Vitest frontend test infra" meantime item — done
while the brief pipeline soaks.

**Two choices worth recording:**
1. **No `@vitejs/plugin-react`.** Its transitive Babel chain (`@rolldown/plugin-babel` → `@babel/core
   8.0.0-rc.4`) conflicts with the modified Next's pinned Babel and fails `npm install`. Vitest 4's built-in
   **oxc** transform handles the React 19 automatic JSX runtime with no plugin, so we dropped it entirely —
   fewer deps, no peer-conflict surface, and a test runner needs none of the plugin's fast-refresh anyway.
2. **Test files stay in the root `tsconfig` include** (not split into a separate test tsconfig). This lets
   `next build` typecheck `*.test.tsx` and the setup file for free — a second safety net — at the cost of
   the build resolving vitest/jest-dom types (already dev-installed). Verified: build stays green with the
   tests present.

**Alternatives considered:** Jest (heavier, needs its own Babel/SWC transform config against modified Next —
the exact conflict we're avoiding); Playwright/E2E (valuable later, but a different layer — this gate is
unit/component, fast, no server). **Reversibility:** high — it's additive dev-only tooling; removing it is
deleting config + tests. Critical-thinker: no pushback, infra is contained and the babel-conflict workaround
is the only non-obvious part (recorded above).

**Verification:** `npm test` → 3 files / 16 tests pass; `npm run build` stays green (test files typecheck).

## D095 — Energy-desk source breadth: NRC via the Federal Register API

**Decision:** Add a fourth ingestion adapter — **NRC documents pulled from the Federal Register API** —
as the Energy desk's regulatory leg. Phase B found Energy consistently the thinnest desk because all three
desks ran on the same capital-flow sources (USAspending grants, EDGAR filings) + arXiv; none carried
*regulatory* signal, where the nuclear/SMR convergence thesis actually becomes enforceable events (combined-
license applications, advanced-reactor rules, HALEU fuel decisions) months ahead of the money or the 8-K.

**Why NRC-via-Federal-Register over EIA (the source fork, operator-decided 2026-06-20):** the two candidate
energy sources have materially different shapes. **EIA** is authoritative *macro* data (generation, storage,
capacity) but (a) needs a free operator-provisioned API key, (b) is monthly/slow so it emits items
infrequently — only a partial fix for *daily* thinness — and (c) is numeric series that need delta/threshold
logic to become "items". **NRC via the Federal Register API** is key-free, public-domain, event-shaped
(daily-ish), squarely on the nuclear/SMR/HALEU convergence thesis, and buildable + live-verifiable end-to-end
with no operator dependency. Chose NRC first; EIA remains a clean follow-on once a key is provisioned.

**How it works:** mirrors the EDGAR/USAspending/arXiv probe model — five on-thesis search terms (small
modular reactor, advanced reactor, high-assay low-enriched uranium, combined license, uranium enrichment),
each filtered to the NRC agency, walked one-probe-per-page by the runner. The term pre-filter is the curation
(keeps signal high) so the significance gate (D085) isn't spending LLM calls on routine license-amendment /
meeting minutiae. A regulatory document has no dollar amount, so it scores on **authority + novelty** like
arXiv — `source_weights['nrc']=0.85` (the NRC is the authoritative nuclear regulator) puts a new record at
≈0.66, comfortably above the materiality floor — and the synthesis model classifies it as a `policy` item
from the text. **Self-activates** in the autonomous pipeline: the daily cron's `supabase db push` seeds the
`source_registry` row (migration `20260620000001`) and `run_ingest.py` reads all `registered_source_ids()`,
so no code path hardcodes the source list.

**Two deliberate v1 scope cuts:**
1. **No entity mentions.** NRC documents carry no ticker/CIK/UEI, so resolution would need name-only trigram
   matching — a linker change (the linker special-cases EDGAR identifiers + USAspending UEI) with false-link
   risk against the precision-gated graph (D091). Records clear materiality without mentions (`entity_type`
   defaults to `company`), so we ship the regulatory *signal* now and defer NRC entity-linking to a focused
   follow-on gate. Cost: NRC items don't yet produce entity chips / convergence.
2. **Fixed rolling lookback, not a forward watermark.** Federal Register pub dates don't lag, but the
   forward-watermark trap is exactly what silently zeroed USAspending (Phase B) — so a 7-day fixed lookback +
   content-hash dedup is the robust default, applied here too.

**Reversibility:** high — additive (one adapter file, one registry line, one weight, one migration). **Critical
-thinker:** no pushback on the source choice (the operator picked it with the EIA tradeoff in hand); the only
non-obvious calls are the two scope cuts above, both recorded.

**Verification:** 24 adapter unit tests against an inline golden fixture (`tests/unit/adapters/test_nrc_adapter.py`);
full backend suite 392 green. Live `fetched>0` confirmation happens on the next cron (or an operator
`run_ingest.py --source nrc` after `supabase db push`).

## D096 — NRC entity-linking via a curated ticker allowlist (completes D095's deferral)

**Decision:** Wire NRC documents into the entity-resolution graph so an NRC notice about Oklo or Centrus
produces an entity chip and feeds cross-desk convergence, like an EDGAR filing or USAspending award. This
completes the scope cut deferred in D095 (#1: "no entity mentions").

**The mechanism choice — exact ticker, not name trigram.** NRC documents carry no ticker/CIK/UEI, so the
obvious route is name-only trigram resolution. But that's fragile precisely for the names we care about:
short company tokens ("Oklo", "Vistra", "Centrus") have few trigrams, so `similarity("OKLO","OKLO INC")`
falls below the resolver's 0.92 auto-link gate — a *correct* match would be recorded unresolved (recall ≈ 0),
or worse, a loose gate would risk false links against the precision-gated graph (D091). Instead we attach a
**known ticker** for thesis-relevant public nuclear/fuel-cycle companies named in a document and resolve via
the resolver's **exact-identifier path** (`find_by_identifier`, confidence 1.0, false-link-proof). A curated
allowlist (Oklo, NuScale, Centrus, BWXT, Constellation, Vistra, Nano Nuclear, Energy Fuels, Uranium Energy,
Cameco, Lightbridge, GE Vernova), matched word-bounded against title + abstract; a name not on the list yields
no mention (no false link), and an attached ticker that happens not to be seeded simply fails to resolve.

**Why a hardcoded allowlist is acceptable here:** the convergence signal only fires when the *same* entity
appears on ≥2 desks — and the entities that appear in NRC docs AND elsewhere are exactly the public nuclear
players, a small, well-known, slow-changing set. A name not on the list has no cross-desk presence to surface
anyway, so the list captures essentially all the convergence value at full precision. Extending it is one line.

**No linker/resolver/generator change.** `extract_resolution_inputs` already reads `mention.get("ticker")`
and `resolve_mention` already does exact-identifier-wins — so emitting ticker-bearing mentions from the adapter
was the entire change. Alternatives rejected: name-only trigram (fragile/false-link risk, above); LLM NER
(per-doc cost + a new eval surface, deferred); a DB reverse-lookup of "any seeded entity named in this text"
(needs new resolver machinery for marginal extra coverage). **Reversibility:** high — additive to one adapter.

**Verification:** +2 adapter unit tests (allowlisted company → ticker mention; word-bounded match; non-match →
no mention); full suite 394 green. Live linking confirmation rides the next cron with an NRC item naming an
allowlisted company → `inspect_brief_entities.py`.

## D097 — Primary-desk routing: a cross-desk record surfaces only on its home desk (desk-bleed fix)

**Problem (operator, reading every desk daily 2026-06-27):** each desk read like an everything-desk. A
record tagged for multiple desks (probes emit a `desk` array, e.g. "hyperscale data center" -> (ai, energy))
was pulled into EVERY tagged desk's brief by `_score_candidates`' `$2 = ANY(nr.desk)` filter, then the D060
convergence boost amplified it. So an Energy project-finance item printed on the AI desk, an autonomous-UAV
arXiv paper printed on AI, etc. — desk identity dissolved.

**Decision:** Route each record to ONE home desk — the first element of its primacy-ordered `desk` array
(`desk[0]`; the EDGAR/adapter probes already list the home desk first, D059). Cross-desk relevance is no
longer a duplicate item; it survives as the convergence *marker* it always should have been — the `desk_count`
materiality boost and the entity-graph chip (D091/D092).

**Mechanism — narrow the OUTPUT, not the fetch.** `_score_candidates` still SELECTs the full cross-desk
neighborhood (`ANY(nr.desk)`) so corroboration counting (D036) and the 90-day amount-normalization window
(D035) keep seeing every related record; only the final material set is filtered to home-desk items via a
pure `_is_home_desk(row, desk)` helper. So a convergence record still corroborates its neighbors and still
earns its boost — it just stops printing on every desk. This keeps the behavior change isolated and testable
(the routing is a pure predicate, not buried in SQL).

**Alternatives rejected:** (a) filter in SQL with `nr.desk[1] = $2` — equivalent output but would also shrink
the corroboration/amount populations and hide the rule inside a query string (harder to unit-test, tautological
test only); (b) dial back the D060 convergence boost — treats the symptom (over-promotion) not the cause
(duplication), and weakens genuine convergence signal. **Reversibility:** high — one predicate, additive.

**Verification:** +4 unit tests pin the predicate (home = `desk[0]`; secondary desk is not home; single-desk
routes to its only desk; empty/missing/None desk routes nowhere); full backend suite 398 green. This is P0
phase 1 (desk demarcation); the widen-the-net epistemic-framing layer is the next gate.

## D098 — Epistemic-framing layer: confidence + attribution on every item (widen-the-net keystone)

**Why:** The operator retired (2026-06-27, stated firmly) the doctrine that had been HPI's spine —
*"every claim cites the public record."* As an admission **gate** it excluded vast amounts of important
signal (reported-not-yet-confirmed, inference, weak signals) for very small benefit and belittled the
reader. Replacement principle: **honesty over exclusion** — cast the net wide, then *grade and attribute
every item transparently* so the **basis and confidence** are visible (estimative language, like real
intelligence analysis). Grounding stays as transparency; it is never again an admission filter. The only
hard line: don't fabricate.

**This gate (P0 phase 2, foundational slice):** introduce the deterministic taxonomy that the rest of the
layer builds on — `engine/engine/brief/epistemics.py`. A single ordered ladder of decreasing certainty,
`Attribution`: CONFIRMED (primary record, citation-supported) → REPORTED (attributed third-party reporting,
not primary) → ANALYSIS (HPI synthesis/inference) → SPECULATIVE (early/weak signal). `classify_item` derives
an item's tier from signals already in the pipeline — the source's evidence class and whether the claim was
citation-supported — with **no LLM call and no new fabrication surface**.

**Key derivation choices:** (a) a `primary` source with a claim that is NOT citation-supported → ANALYSIS,
not dropped — this is the literal suppress→label flip the philosophy demands (the old D069 gate deleted that
sentence). (b) A `signal` source (GDELT, D082) caps at SPECULATIVE — radar, never a cited fact. (c) An
UNCLASSIFIED source defaults to REPORTED, never PRIMARY/CONFIRMED — widening the net must not silently
inflate confidence; a future private-AI newsroom/DoD-press source (P3) maps to `reported` deliberately.

**Scope cut (deliberate):** this gate is the vocabulary + pure derivation + tests only. The behavioral wiring
— flipping the publish path from *exclude under-grounded* (D070/D072) to *keep-and-label*, persisting the
label, and rendering the reader chip — is the NEXT gate, because the publish-gate flip is the behaviorally
risky core and is naturally coupled to threading per-item source_id + grounding outcome. Anti-fabrication
(`eval_analysis`, D071/D073) is untouched and remains the one hard line. **Reversibility:** high — additive
pure module, nothing wired yet.

**Verification:** 11 unit tests pin the ladder ordering, the source→evidence map (incl. the honest unknown
→ reported default), and every `classify_item` branch (primary+cited=confirmed, primary+uncited=analysis,
signal=speculative, reported caps, analysis_only). Full backend suite 409 green.

## D099 — Publish-path flip: grounding becomes a per-item confidence label, not a suppression gate

**Why:** Completes the widen-the-net direction (information-philosophy 2026-06-27; D098 built the
taxonomy). The operator retired *"every claim cites the public record"* as an **admission gate**. The
literal mechanism of that gate was the D070 publish floor — a brief with fewer than `brief_min_claims`
(3) provable claims was marked `failed` and withheld — so an honest-but-thin desk went dark on a quiet
day. That is the suppression the memory names: *"the publish-floor + grounding gates must become
confidence/attribution labels, not suppression."*

**Decision:** `evaluate_brief` no longer gates publication on a provable-claim count. It publishes when
the brief has **≥1 honest item**, and stamps every surviving item with an epistemic **attribution** label
(`classify_item`, D098) derived from its dominant cited source + whether its claims were citation-supported:
confirmed / reported / analysis / speculative. `provable_claims` is retained as a quality metric and as the
best-attempt tiebreak for the regen loop (D072), which now retries only a genuinely empty draw or a
generation exception.

**The hard line is unchanged.** An item whose claims have NO source support is still excluded (D069) — that
is not suppressing signal, it is refusing to dress an unsupported guess as a confirmed fact. Per-sentence
citation stripping in the generator and the analysis grounding gate (D071/D073) are untouched; fabrication
remains the one thing that blocks content.

**What changes in practice, today:** thin desks publish (labeled) instead of going dark; every item now
carries a `brief_items.attribution` column (migration 20260628000001, default `confirmed` — accurate, since
the pre-D099 ledger was all cited-confirmed) surfaced through the briefs API. The non-`confirmed` tiers are
wired and ready: they light up when reported-news / signal sources feed items (P3), without a citation gate
excluding them.

**Editorial floor (open knob):** the publish minimum is ≥1 surviving item. If the operator wants a thicker
"enough to publish" bar, that is a one-line change; it is intentionally NOT a grounding gate.

**Scope cut:** the reader confidence chip (rendering the label in `web/`) is the next gate — frontend-only,
exposed via the API field added here. **Reversibility:** moderate — the gate logic and a column; the column
is additive.

**Verification:** publish tests rewritten to the new contract (thin brief publishes; zero-support item still
excluded; survivors carry a valid attribution; regen retries an empty draw); full backend suite 411 green.
Live confirmation rides the next cron + an operator brief inspection. Bucket C mechanism docs (SPEC,
ARCHITECTURE) updated; the frozen Gate-1 CONTRACT carries a dated addendum rather than an in-place rewrite.

## D100 — Brief is a comprehensive desk read: raise the item ceiling to 25, supersede D039

**Decision (operator directive, 2026-06-28):** A desk brief is a *comprehensive picture of the domain*,
not a five-minute skim. Supersede D039's `BRIEF_MAX_ITEMS=8` ("practical upper bound for a sub-5-minute
read") with **25**. Rework the synthesis prompt accordingly: write one substantive item per genuinely
material development up to the cap (was hard-instructed to "target 2–3 items" — a thinness cause as real as
the cap itself), enrich the BLUF into a 4–6 sentence state-of-the-domain narrative (was a 2–3 sentence
teaser), and add explicit desk-discipline ("include only developments whose center of gravity is THIS desk")
to reinforce the D097 primary-desk routing at the synthesis layer.

**Why:** The operator's product judgment: a handful of items per desk is not a saleable intelligence product;
HPI must show the domain thoroughly. The arbitrary "scannable in 5 minutes" framing was rejected.

**Guardrails kept (quality over quota):** the prompt forbids padding, splitting one development across items,
duplication, and manufacturing items the passages don't support — "if material is thin, write fewer strong
items rather than weak filler." The significance gate (D085) is UNCHANGED: more content must come from more
*sources*, never from loosening the froth filter (SPAC/shell/obituary noise stays dropped). The D099 publish
posture is unchanged: a desk still publishes whatever quality items it has.

**Honest limitation — the ceiling is not the fill.** Raising the cap and unblocking the prompt is necessary
but NOT sufficient: real output is **supply-limited**. With only 4 source adapters built (USAspending, EDGAR,
arXiv, NRC) and froth filtered out, desks produce ~3–6 quality items today regardless of the cap. The cap
fills toward 25 only as **source breadth (P3)** grows — building the unbuilt Tier-0 veins (SAM.gov, DoD
contracts, Congress.gov, EIA, FERC/ISO), the news/trade-press *reported* tier (now publishable under D098/
D099), and GDELT-as-story. That source build is the next major effort; this decision is the ceiling-raise
that lets it land without re-tuning the cap.

**Cost note:** up to 25 LLM-synthesized items/desk × 3 desks raises per-run synthesis + analysis + eval cost
roughly linearly; the daily budget guard still applies. Acceptable at current absolute scale.

**Verification:** prompt unit tests (persona + citation discipline) green; full suite 411 green. Live effect
rides the next cron once deployed. **Reversibility:** trivial — `BRIEF_MAX_ITEMS` is one env var.
