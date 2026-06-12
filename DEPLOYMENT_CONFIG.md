# Deployment Configuration — Hard Power Intelligence (Cycle 1)

Gate 9 (`deploy_ready`) artifact. Defines the production topology, the deploy steps per
service, and the full environment/secrets matrix. Architecture per **D009** (Vercel +
Fly.io + Supabase) and **D050** (Lemon Squeezy payments).

> Status: **API deployable; worker + cloud provisioning pending.** The `hpi-api` image
> builds and runs (`/health` 200, verified locally). The `hpi-worker` has no code yet, and
> cloud accounts/secrets are not provisioned. See [§6 Outstanding](#6-outstanding-before-first-deploy).

---

## 1. Topology

```
                    ┌────────────────────────┐
   subscribers ───► │  Vercel — Next.js web  │  (SSR/ISR, marketing + reader)
                    └───────────┬────────────┘
                                │ server-to-server (FASTAPI_INTERNAL_URL, no CORS, D011)
                                ▼
                    ┌────────────────────────┐        ┌─────────────────────────┐
                    │  Fly.io — hpi-api      │◄──────►│  Supabase (managed PG)  │
                    │  (FastAPI)             │        │  Postgres + pgvector +   │
                    └────────────────────────┘        │  Auth + Storage + RLS    │
                    ┌────────────────────────┐        └─────────────────────────┘
                    │  Fly.io — hpi-worker   │◄──────────────┘ (procrastinate queue, D004)
                    │  (persistent ingest)   │
                    └────────────────────────┘
   Lemon Squeezy (MoR) ──► webhook ──► hpi-api  POST /v1/webhooks/lemon-squeezy (D050)
```

| Service | Platform | Notes |
|---------|----------|-------|
| `web` (Next.js) | **Vercel** | SSR/ISR; the only public surface. Reads data via FastAPI. |
| `hpi-api` (FastAPI) | **Fly.io** | Single data boundary (D011). Not publicly browsable beyond `/health` + webhook. |
| `hpi-worker` (procrastinate) | **Fly.io** | Persistent (never sleeps — D009); owns ingestion schedule (D004). |
| Database / Auth / Storage | **Supabase** | Managed Postgres + pgvector + Auth + Storage. Migrations in `supabase/migrations/`. |
| Payments | **Lemon Squeezy** | Merchant of Record (D050); hosted checkout + HMAC webhook. |
| Errors | **Sentry** | Optional; inits only when DSN present. |

---

## 2. Deploy order (first launch)

1. **Supabase** — create cloud project; `supabase db push` to apply all migrations
   (incl. `20260611000001_lock_briefs_rls.sql`); capture project URL, anon key, service
   role key, JWT secret, pooled `DATABASE_URL`.
2. **hpi-api → Fly.io** — `fly deploy` with `docker/Dockerfile.api`; set secrets (§4).
3. **hpi-worker → Fly.io** — `fly deploy` with `docker/Dockerfile.worker`; set secrets.
4. **web → Vercel** — connect repo (root `web/`), set env (§4), deploy. Point
   `FASTAPI_INTERNAL_URL` at the private Fly.io api address.
5. **Lemon Squeezy** — create store/product, set the webhook URL to
   `https://<api-host>/v1/webhooks/lemon-squeezy`, capture API key + webhook secret.
6. Smoke test: signup → brief renders → checkout (test mode) → webhook updates tier.

---

## 3. Environment matrix

Legend: 🔒 secret (never commit) · 🌐 public (safe in client bundle).

### web (Vercel)
| Var | Type | Example / source |
|-----|------|------------------|
| `NEXT_PUBLIC_SUPABASE_URL` | 🌐 | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | 🌐 | Supabase anon key |
| `FASTAPI_INTERNAL_URL` | 🔒 | Private Fly.io api URL, e.g. `https://hpi-api.internal/v1` |

### hpi-api (Fly.io)
| Var | Type | Source |
|-----|------|--------|
| `DATABASE_URL` | 🔒 | Supabase pooled connection (asyncpg). Direct PG role — bypasses RLS (D011). |
| `SUPABASE_URL` | 🔒/🌐 | For JWKS endpoint (JWT verification) |
| `SUPABASE_JWT_SECRET` | 🔒 | HS256 fallback verification; **≥32 chars** |
| `CORS_ALLOW_ORIGINS` | 🔒 | The real web origin(s), comma-separated. **No `*`.** |
| `ENVIRONMENT` | — | `production` |
| `LEMONSQUEEZY_API_KEY` | 🔒 | Lemon Squeezy |
| `LEMONSQUEEZY_STORE_ID` | 🔒 | Lemon Squeezy |
| `LEMONSQUEEZY_WEBHOOK_SECRET` | 🔒 | **Required before payments go live** (else webhook degrades to accept-and-ignore, D045) |
| `OPENROUTER_API_KEY` | 🔒 | LLM waterfall (D006) — used by brief generation |
| `SENTRY_DSN` | 🔒 | Optional |

### hpi-worker (Fly.io)
| Var | Type | Source |
|-----|------|--------|
| `DATABASE_URL` | 🔒 | Same Supabase connection |
| `OPENROUTER_API_KEY` | 🔒 | LLM calls during ingestion/synthesis |
| `SENTRY_DSN` | 🔒 | Optional |

---

## 4. Secrets you must provision (human action)

These cannot be generated by code — gather before first deploy:

- [ ] **Supabase cloud project** → URL, anon key, service role key, JWT secret, `DATABASE_URL`
- [ ] **Fly.io account** + `flyctl` auth; two apps created (`hpi-api`, `hpi-worker`)
- [ ] **Vercel project** linked to repo (`web/` as root)
- [ ] **Lemon Squeezy** store + product → API key, store ID, webhook signing secret
- [ ] **OpenRouter** API key (LLM waterfall)
- [ ] **Sentry** DSN (optional)
- [ ] Production domain + DNS (Vercel) and TLS (automatic on Vercel/Fly)

---

## 5. Pre-deploy gate checklist (D044 / Gate 7-8)

- [x] `uv sync --all-packages --all-extras` provisions cleanly (D052)
- [x] `bash run-tests.sh` green — backend pytest + `next build` (D052)
- [x] Security audit PASS, 0 Critical/High (SECURITY_AUDIT.md)
- [x] Briefs-RLS paywall lock-down migration written (`20260611000001_lock_briefs_rls.sql`)
- [ ] Migration applied to cloud (`supabase db push`) and verified
- [ ] `ENVIRONMENT=production`, real `CORS_ALLOW_ORIGINS`, JWT secret ≥32 set
- [ ] Lemon Squeezy webhook secret configured

---

## 6. Outstanding before first deploy

- ✅ **`docker/Dockerfile.api`** + **`fly.api.toml`** — written and **verified locally**
  (image builds; container serves `/health` 200). Ready for `fly deploy --config fly.api.toml`.
- ✅ **`.dockerignore`** — keeps the build context to the uv workspace.
- 🚧 **`docker/Dockerfile.worker`** + **`fly.worker.toml`** — written as **templates**, but
  **`hpi-worker` has no code** (`worker/tasks/` is empty — no procrastinate App or periodic
  schedule, D004). Must implement the worker before it can deploy. Until then, ingestion/
  brief generation runs manually (e.g. the brief script) rather than on a schedule.
- ⬜ **Cloud provisioning + secrets** — Supabase project, Fly.io apps, Vercel project, and
  all secrets in §4 are not yet set up (human action).
- ⬜ **Vercel project config** — root directory `web/`, env wiring, build command.
- ⬜ **Apply RLS migration to cloud** — `supabase db push` (`20260611000001_lock_briefs_rls.sql`).
- ⬜ **CI deploy workflow** (optional) — `.github/workflows/meridian.yml` runs only
  structural verify; it does not build/test the app or deploy. A deploy pipeline (or manual
  `fly deploy` + Vercel git integration) is needed.

**Decision point for launch:** Cycle 1 can go live as **web + api + manual brief generation**
(worker deferred), or wait until the scheduled `hpi-worker` is built. The former gets the
product in front of subscribers sooner; the latter automates the daily cadence.
