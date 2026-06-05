# Contract — Hard Power Intelligence, Cycle 1

Scope, stack, deployment, and constraints for the Cycle 1 build.
This document is the Gate 1 artifact. Update it if scope changes; a scope change
requires re-passing Gate 1.

---

## What we are building

A web-based intelligence subscription product. An automated engine ingests public
government, regulatory, and financial data, resolves every mention to a canonical
entity (company → ticker → CIK → contractor ID), and synthesizes a daily
source-grounded BLUF brief for the Defense sector. Every claim in the brief links
to its source. Subscribers read it on the web. A citation-faithfulness eval harness
runs on every brief before publish; briefs below the threshold do not ship.

**Cycle 1 scope: Defense desk, web-only.** One vertical deep before three shallow.

---

## Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Web frontend | Next.js (App Router) on Vercel | Marketing, reader, Stripe checkout |
| API backend | FastAPI (Python) | Brief API, auth, Stripe webhooks, scheduler endpoint |
| Database / auth | Supabase (Postgres + pgvector) | Graph, records, briefs, users, vectors, RLS |
| Intelligence engine | Python (adapter → resolver → brief gen → eval) | Runs as background worker |
| Scheduler | APScheduler + Postgres job queue | `FOR UPDATE SKIP LOCKED`; upgrade to Celery only if scale demands |
| LLM | Anthropic API | Cheap models for extraction/clustering; strong model for synthesis |
| Payments | Stripe | Web-first reader model; subscriptions managed on web |
| Email | Resend | Transactional and digest emails |
| Errors | Sentry | Both frontend and backend |
| Analytics | PostHog | Product analytics (not trading signals) |
| DNS / WAF | Cloudflare | |

---

## Deployment targets

| Service | Platform | Notes |
|---------|---------|-------|
| Next.js web | Vercel | Hobby → Pro as traffic grows |
| FastAPI backend | Fly.io or Railway | Single region at MVP; scale later |
| Supabase | Supabase cloud | Free → Pro at ~500MB or 50k MAU |

---

## Data sources — Cycle 1 (Tier 0, free)

USAspending API · SAM.gov · DoD daily contracts page · Congress.gov ·
DSCA Foreign Military Sales · EDGAR (SEC filings) · FRED · BLS · FINRA ·
Finnhub (free tier) · Financial Modeling Prep (~$19/mo) · Google News RSS · GDELT

No paid enterprise feeds in Cycle 1. FMP is the one cheap upgrade (~$19/mo).

---

## Acceptance criteria — Cycle 1 complete when:

1. A cited daily Defense brief renders on web; every claim links to its source.
2. The citation-faithfulness eval harness reports at or above the target threshold
   before any brief is published.
3. A user can register, subscribe via Stripe (test → live), and read gated content.
4. The intelligence engine runs within the monthly LLM budget cap.
5. Infrastructure runs within the ~$80–230/mo envelope.

---

## Out of scope — Cycle 1

- **Energy and AI-Infrastructure desks** — Cycle 2.
- **Mobile apps** (React Native / Expo, App Store, Google Play) — Cycle 2.
- **Second-order supply-chain synthesis** (`SUPPLIES`/`PARENT_OF` traversal) — Cycle 2.
- **Personalized portfolios, trade signals, buy/sell recommendations** — never.
- **Plaid integration** — never (breaks cost model and non-advice posture).
- **Paid enterprise data** (Bloomberg, AlphaSense, FactSet, real-time feeds) —
  deferred until revenue funds it.
- **Creator / RIA / Team subscription tiers** — after base product has paying users.

---

## Regulatory posture

HPI is a **general publication**, not personalized investment advice. It sits in the
publishers' exemption lane: it reports on sectors and events, never tells a specific
user what to do with their portfolio. No buy/sell recommendations. No personalized
portfolios. Personalization = filtering/reordering the shared brief by followed
entities only.

*This is a product-design posture, not legal advice.*

---

## Budget guardrails

- LLM spend: budget guard pauses synthesis if daily cost exceeds cap.
- Data spend: Tier-0 sources are free; FMP ~$19/mo is the only Cycle-1 paid source.
- Infrastructure: stay inside the $80–230/mo envelope at MVP scale.
- Break-even: designed to reach profitability at a small number of paying subscribers.
