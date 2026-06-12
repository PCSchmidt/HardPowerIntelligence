# Deploy Runbook — Hard Power Intelligence (Cycle 1, first deploy)

A step-by-step, copy-paste runbook for the **first** production deploy of the Defense
desk: Supabase (cloud) → Fly.io (`hpi-api`) → Vercel (`web`), plus an interim daily-brief
cadence via GitHub Actions. Architecture per [DEPLOYMENT_CONFIG.md](DEPLOYMENT_CONFIG.md)
(D009, D011, D050).

> **✅ First deploy completed 2026-06-12** — live at `hard-power-intelligence.vercel.app`
> + `hpi-api.fly.dev`. Real-world gotchas hit along the way (keep for next time):
> (1) `supabase db push` needs the **URL-decoded** DB password in `SUPABASE_DB_PASSWORD`
> (the connection string stores it percent-encoded); (2) intermittent local DNS failures
> resolving the Supabase pooler host — retry; (3) two prod-only bugs fixed —
> ivfflat→HNSW index (D053) and `pyjwt[crypto]` for ES256 tokens (D054); (4) Fly now
> requires a payment method before deploy. Remaining work in DEPLOYMENT_CONFIG.md §6.

> **Scope of this deploy.** Web + API + a brief generated from data already in the DB.
> This validates the whole serving + auth + payments path end-to-end. It does **not**
> include live scheduled ingestion of fresh government data — there is no production
> ingestion runner yet (the `hpi-worker` is unbuilt, D004). See [§6](#6-the-cadence-honestly)
> for exactly what the scheduled job does and does not do.

> **Cost note.** `run_brief.py` calls paid LLMs (OpenRouter + OpenAI embeddings, D006).
> A daily run is a few cents; don't enable the schedule until you have data worth briefing.

---

## 0. Pre-flight checklist

**Accounts (you create these — I can't):**
- [ ] Supabase project — **you already have this** ✅
- [ ] Fly.io account (`https://fly.io`)
- [ ] Vercel account (`https://vercel.com`)
- [ ] OpenRouter API key (`https://openrouter.ai`)
- [ ] OpenAI API key (embeddings — `text-embedding-3-small`)
- [ ] Anthropic API key (optional — last-resort LLM fallback, D006)
- [ ] Lemon Squeezy store (test mode is fine for first deploy, D050)
- [ ] GitHub repo already exists ✅ (`PCSchmidt/HardPowerIntelligence`)

> Railway is **not** used — D009 chose Fly.io over Railway (Railway sleeps idle services).

**CLIs (install locally):**
```bash
# Supabase CLI (you likely have it — `supabase --version`)
# Fly.io
curl -L https://fly.io/install.sh | sh        # then add to PATH; `fly version`
fly auth login
# Vercel
npm i -g vercel                                # `vercel --version`
vercel login
# GitHub CLI (for setting Actions secrets) — `gh --version`; `gh auth login`
```

**Values to collect from the Supabase dashboard** (Project → Settings):
- [ ] Project ref (the 20-char id in the project URL `https://<ref>.supabase.co`)
- [ ] `SUPABASE_URL` = `https://<ref>.supabase.co`
- [ ] anon key (Settings → API)
- [ ] service_role key (Settings → API) — **secret**
- [ ] JWT secret (Settings → API → JWT Settings) — only needed if your project still uses
      the legacy HS256 secret; new projects use asymmetric keys verified via JWKS (the API
      handles both — `api/app/deps.py`)
- [ ] `DATABASE_URL` — **use the Session-mode pooler (port 5432), NOT Transaction (6543).**
      asyncpg uses prepared statements (`engine/db.py`), which break on the Transaction
      pooler (PgBouncer). Settings → Database → Connection pooling → **Session mode** → URI:
      `postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`
      (the Session pooler is also IPv4, which GitHub Actions needs in §6).

---

## 1. Supabase (cloud) — schema + initial data

### 1.1 Link the local project to your cloud project
```bash
cd <repo-root>
supabase login                       # if not already
supabase link --project-ref <ref>
```
**Verify:** `supabase projects list` shows your project with a ● in the linked column.

### 1.2 Apply migrations (includes the RLS paywall lock-down)
```bash
supabase db push
```
This applies all `supabase/migrations/*.sql`, including
`20260611000001_lock_briefs_rls.sql` (Gate 8 fix).

**Verify:**
```bash
supabase db diff           # should report NO schema differences (local == cloud)
```
Or in the dashboard (Table editor) confirm the 16 tables exist and RLS is **on** for
`briefs`, `subscriptions`, `user_profiles`, etc.

### 1.3 Seed initial data (so there's something to brief)
`run_brief.py` reads `normalized_records`; on a fresh DB that table is empty and brief
generation will no-op. Seed the golden fixture once:
```bash
DATABASE_URL='<cloud DATABASE_URL>' uv run python scripts/seed_fixtures.py
```
**Verify:**
```bash
# row count > 0
psql '<cloud DATABASE_URL>' -c "select count(*) from normalized_records;"
```

---

## 2. Fly.io — deploy `hpi-api`

### 2.1 Create the app (name must be globally unique)
```bash
cd <repo-root>
fly apps create hpi-api          # if taken, pick e.g. hpi-api-pcs and update `app` in fly.api.toml
```
**Verify:** `fly apps list` includes the app.

### 2.2 Set secrets (staged — does not deploy yet)
```bash
fly secrets set --stage --app hpi-api \
  DATABASE_URL='<cloud DATABASE_URL>' \
  SUPABASE_URL='https://<ref>.supabase.co' \
  SUPABASE_JWT_SECRET='<jwt-secret-if-HS256-else-any-placeholder>' \
  OPENROUTER_API_KEY='<openrouter>' \
  OPENAI_API_KEY='<openai>' \
  ANTHROPIC_API_KEY='<anthropic-or-empty>' \
  LEMONSQUEEZY_WEBHOOK_SECRET='<ls-webhook-secret>'
# Note: the Lemon Squeezy CHECKOUT creds (API key, store id, variant ids) go in VERCEL,
# not here — the checkout route runs on Vercel (web/app/api/checkout/route.ts). The API
# only needs the WEBHOOK secret (it verifies inbound webhooks). CORS_ALLOW_ORIGINS is set
# in step 4.2 once the Vercel URL exists.
```
**Verify:** `fly secrets list --app hpi-api` shows the names (values are hidden).

### 2.3 Deploy
```bash
fly deploy --config fly.api.toml --app hpi-api
```
**Verify:**
```bash
fly status --app hpi-api                       # machine "started", health check passing
curl https://hpi-api.fly.dev/health            # {"status":"ok",...}
# authed route should 401 WITHOUT a token (proves auth is wired, not that it's broken):
curl -s -o /dev/null -w "%{http_code}\n" https://hpi-api.fly.dev/v1/briefs/latest?desk=defense
# → 401
```
Record the API base URL: **`https://hpi-api.fly.dev/v1`** (note the `/v1`; `/health` has no prefix).

---

## 3. Vercel — deploy `web`

### 3.1 Link the project (web/ as root)
```bash
cd web
vercel link            # choose your scope; create new project "hard-power-intelligence"
```
> In the Vercel dashboard, set **Root Directory = `web`** if it didn't auto-detect.

### 3.2 Set environment variables
```bash
# Public (browser-safe):
vercel env add NEXT_PUBLIC_SUPABASE_URL production      # https://<ref>.supabase.co
vercel env add NEXT_PUBLIC_SUPABASE_ANON_KEY production # anon key
# Server-only (the data boundary, D011):
vercel env add FASTAPI_INTERNAL_URL production          # https://hpi-api.fly.dev/v1
```
**Verify:** `vercel env ls` lists all three under `production`.

### 3.3 Deploy
```bash
vercel --prod
```
**Verify:** open the printed URL; the marketing home renders. Record the domain, e.g.
`https://hard-power-intelligence.vercel.app`.

---

## 4. Wire the two together + smoke test

### 4.1 Point the webhook at the API (Lemon Squeezy dashboard)
Set the webhook URL to `https://hpi-api.fly.dev/v1/webhooks/lemon-squeezy`; signing secret
must match `LEMONSQUEEZY_WEBHOOK_SECRET` (step 2.2).

### 4.2 Set API CORS to the web origin (defense-in-depth)
```bash
fly secrets set --app hpi-api CORS_ALLOW_ORIGINS='https://hard-power-intelligence.vercel.app'
# (triggers a rolling restart)
```

### 4.3 End-to-end smoke test (browser)
- [ ] Visit the Vercel URL → marketing home renders
- [ ] Sign up → confirm a row appears in `user_profiles` (Supabase) via the `handle_new_user` trigger
- [ ] Log in → `/desk/defense` renders the seeded brief (proves web → FastAPI → DB → RLS path)
- [ ] Start checkout (Lemon Squeezy **test mode**) → complete → confirm `subscriptions` row + tier flips to `pro`
- [ ] Confirm a **free** user cannot read the archive directly (paywall fix): with a logged-in
      free user's JWT, `curl 'https://<ref>.supabase.co/rest/v1/briefs?select=*' -H "apikey: <anon>" -H "Authorization: Bearer <user-jwt>"` → **empty array** (RLS/REVOKE working)

---

## 5. Generate the first published brief
```bash
DATABASE_URL='<cloud DATABASE_URL>' \
OPENROUTER_API_KEY='<...>' OPENAI_API_KEY='<...>' \
uv run python scripts/run_brief.py --desk defense
```
**Verify:** output prints `Eval: PASSED` and `status=published`; the brief now appears at
`/desk/defense` on the live site.

---

## 6. The cadence, honestly

`scripts/run_brief.py` **synthesizes a brief from whatever is already in `normalized_records`**.
It does **not** fetch fresh government data — there is no production ingestion runner yet
(that is the unbuilt `hpi-worker`, D004). So:

- **Today:** scheduling `run_brief.py` re-runs synthesis on the *current* data. Useful for a
  fixed sample/demo brief, not for genuinely fresh daily intelligence.
- **For real fresh cadence:** build an ingestion runner (USAspending adapter → entity
  resolver → `normalized_records`) and run it *before* `run_brief.py`. That is the next
  engineering task after this deploy (the durable Fly worker, or a second scheduled step).

### Interim scheduled job — GitHub Actions
A scheduled workflow is provided at [.github/workflows/daily-brief.yml](.github/workflows/daily-brief.yml).
It is **manual-trigger by default**; the daily `cron` is included but commented until real
ingestion exists (so you don't pay to regenerate the same brief nightly).

**Set the Actions secrets:**
```bash
gh secret set DATABASE_URL --body '<cloud DATABASE_URL>'
gh secret set OPENROUTER_API_KEY --body '<...>'
gh secret set OPENAI_API_KEY --body '<...>'
gh secret set ANTHROPIC_API_KEY --body '<...>'   # optional
```
**Verify (manual run):**
```bash
gh workflow run "Daily Brief" -f desk=defense
gh run watch
```
Confirm a new published brief appears on the live site.

> **Why GitHub Actions for the bridge, not Fly?** It's the lowest-ops option for a solo
> operator — no extra image or app to maintain, full cron control, logs and on/off in one
> place. The durable Fly worker is the eventual home once ingestion needs retries and
> multi-source orchestration (don't build that until the manual cadence actually hurts).

---

## 7. Rollback / teardown

| Action | Command |
|--------|---------|
| Roll back API | `fly releases --app hpi-api` then `fly deploy --image <previous> --app hpi-api` |
| Roll back web | Vercel dashboard → Deployments → promote previous |
| Roll back a migration | write a new down-migration; Supabase has no auto-down — never edit an applied migration |
| Pause spend | disable the GitHub workflow; `fly scale count 0 --app hpi-api` |

---

## Post-deploy checklist
- [ ] `/health` 200 on Fly; web renders on Vercel
- [ ] Signup → login → brief renders (web → API → DB)
- [ ] Free user cannot read the archive via direct PostgREST (paywall fix verified)
- [ ] Checkout (test mode) flips tier to `pro`
- [ ] `ENVIRONMENT=production`, real `CORS_ALLOW_ORIGINS`, JWT secret ≥32 (if HS256)
- [ ] First brief published and visible
- [ ] CHANGELOG.md updated + tag `v1.0.0` when Gate 9 `GO` is given
