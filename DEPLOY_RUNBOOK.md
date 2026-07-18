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
> This validates the whole serving + auth + payments path end-to-end. A production ingestion
> runner (`scripts/run_ingest.py`, D057) pulls fresh data in the GitHub Actions job (§6). The
> always-on `hpi-worker` (D116) is now built and owns **GDELT** ingestion off CI (persistent
> IP — see [§2.5](#25-flyio--deploy-hpi-worker-gdelt)); every other source runs in CI.

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

### 1.3 Seed the entity-resolution reference set (T3.1/T3.2, D091)
The entity graph (the moat) resolves brief mentions to investable entities. Seed the public
universe and verify the resolver's accuracy before relying on it:
```bash
uv run python scripts/seed_entities.py        # ~8k public companies from SEC (idempotent; re-run to resume)
uv run python scripts/renormalize_aliases.py  # backfill alias_normalized after a normalize_mention change
uv run python scripts/eval_resolver.py        # accuracy gate vs tests/fixtures/entity_golden.json
```
`eval_resolver.py` must report **PASS** (precision ≥ `entity_resolver_min_precision`, default 0.95) —
a wrong ticker corrupts the provenance trust model, so resolved entities don't render until this passes.
It prints per-miss diagnostics (status / confidence / top trigram candidates) to guide tuning. Seed is
idempotent (de-duped by CIK, NOT EXISTS guard), so it's safe to re-run after a connection drop. Private /
venture entities are minted later from ingest identifiers (UEI/CIK), not seeded here.

`renormalize_aliases.py` is only needed after changing `normalize_mention` — the seed is
insert-if-not-exists, so it won't rewrite already-stored `alias_normalized`; this idempotent backfill does
(it recomputed 301 aliases when the SEC `/DE/` jurisdiction-tag strip landed, lifting recall 0.889 → 1.000).

**After a brief runs with the linker** (T3.3), verify what got linked/minted before trusting the chips:
```bash
uv run python scripts/inspect_brief_entities.py [desk]   # read-only; per-item entities + minted list
```
Look for correct ticker links and sane minting (real private contractors, not garbage). The brief logs
`entities_linked items_with_entities=N` per desk; linking is best-effort and never darks a brief.

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
> **Builder DNS gotcha (hit 2026-06-16):** flyctl now defaults to the **Depot** remote builder
> (`api.depot.dev`). On a flaky/filtered network the build fails with
> `dial tcp: lookup api.depot.dev: no such host`. Fallbacks, in order:
> `--depot=false` (use Fly's own remote builder) → `--local-only` (build with local Docker, only
> needs `registry.fly.io`; requires Docker Desktop running). The `--local-only` path is what
> succeeded here.

**Verify:**
```bash
fly status --app hpi-api                       # machine "started", health check passing
curl https://hpi-api.fly.dev/health            # {"status":"ok",...}
# authed route should 401 WITHOUT a token (proves auth is wired, not that it's broken):
curl -s -o /dev/null -w "%{http_code}\n" https://hpi-api.fly.dev/v1/briefs/latest?desk=defense
# → 401
```
Record the API base URL: **`https://hpi-api.fly.dev/v1`** (note the `/v1`; `/health` has no prefix).

### 2.5 Fly.io — deploy `hpi-worker` (GDELT)

> **RETIRED 2026-07-17 — `hpi-worker` is gone; skip this section.** GDELT's DOC API IP-blocks Fly (not
> just CI), so the worker never worked and GDELT is parked (see the `gdelt-ingestion-saga`). The app was
> destroyed; **all ingestion now runs in GitHub Actions** (`daily-brief.yml`, `run_ingest.py` — no
> `--exclude gdelt` needed since GDELT isn't fetched). The steps below are kept for history only.

The always-on worker (D116) owned **GDELT** ingestion: a persistent IAD IP was meant to clear the HTTP
429 that the shared GitHub Actions IP hits. It ingested into the same DB on a 3h loop; CI ran every
other source (`run_ingest.py --exclude gdelt`). New always-on machine — ~$2–4/mo.

```bash
fly apps create hpi-worker                        # if taken, update `app` in fly.worker.toml
fly secrets set --config fly.worker.toml \
  DATABASE_URL='<same pooled URL as hpi-api>' \
  OPENAI_API_KEY='<embeddings key>'               # else news lands un-embedded (no RAG)
fly deploy --config fly.worker.toml --depot=false # Depot DNS gotcha: same as §2.3
fly scale count 1 --config fly.worker.toml        # exactly one — >1 double-ingests
```

**Verify:**
```bash
fly logs --config fly.worker.toml                 # look for: worker_ingest source=gdelt status=success
# and confirm GDELT rows re-appear in the DB while CI's ingest no longer lists gdelt.
```
> If the first pulls log `status=skipped`, GDELT's circuit breaker may still be open from earlier CI
> 429s — it clears on the cooldown's trial run (D077). CI no longer touches GDELT, so it stays closed.

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

`scripts/run_ingest.py` now **fetches fresh government data** into `normalized_records`
(D057), and `scripts/run_brief.py` **synthesizes a brief from it**. The two run in sequence
(ingest → brief). So:

- **Today:** `run_ingest.py` pulls fresh data from **USAspending** (defense-tech awards, D059)
  and **SEC EDGAR** (cross-desk filings, D061) — dedup + embed + cursor + retention — then
  `run_brief.py --desk <defense|ai|energy>` synthesizes from it (D062). `daily-brief.yml` runs
  both (ingest first; `skip_ingest=true` regenerates from existing data; desk is selectable).
  Use `run_ingest.py --reset-cursor` to re-pull the full window after changing a source filter.
- **Still pending:** dedicated AI/Energy sources for depth (EIA/NRC + interconnection queues),
  EDGAR follow-ons (capex, Form 4/13F), and the durable always-on `hpi-worker` (D004) — only
  needed once the manual/Actions cadence actually hurts.
- **Fixtures retired:** the Defense desk now publishes from live-ingested data. To re-pull and
  re-publish: `uv run python scripts/run_ingest.py` then `run_brief.py --desk defense`
  (DATABASE_URL + OPENAI_API_KEY from `.env`).

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

**Migration reconcile (safeguard).** The workflow runs `supabase db push --db-url "$DATABASE_URL"`
*before* ingest/brief, so a schema migration merged to `main` is applied to the remote DB before any
code that references it runs — the cron runs latest `main`, so without this, code + schema could desync
and dark a brief. The step is **non-fatal**: app columns are written defensively (e.g. `signal_series`
is best-effort, D089), so a reconcile hiccup warns and proceeds rather than blocking publishing. It
reuses `DATABASE_URL` (no project link/login needed). **Caveat:** `db push` takes a session advisory
lock, which the **transaction-mode pooler doesn't support** — if `DATABASE_URL` is the pooler, the step
will *warn* instead of applying. If that happens, add a direct-connection secret (e.g.
`gh secret set SUPABASE_DB_URL_DIRECT --body '<direct 5432 URL>'`) and point the reconcile step at it.
Check the first scheduled run's "Reconcile DB migrations" step logs for `Migrations reconciled` vs the
warning to know which case you're in. You can still run `supabase db push` manually anytime.

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


## 8. Custom domain cutover — hardpowerintel.com (D083)

**No app code changes.** Every redirect is origin-relative (`checkout/route.ts` uses
`new URL(request.url).origin`; signup/oauth use `window.location.origin`), so the switch is
pure dashboard config. Do it BEFORE onboarding testers, so their magic links + sessions settle
on the final domain once (changing it mid-test breaks active links).

### 8.1 Vercel — add the domain
- Vercel → the web project → Settings → Domains → add `hardpowerintel.com` and `www.hardpowerintel.com`.
- Make the apex (`hardpowerintel.com`) primary; Vercel auto-redirects `www` → apex.
- Vercel displays the exact DNS records to create — note them (apex A record, currently `76.76.21.21`; `www` CNAME `cname.vercel-dns.com`).

### 8.2 Cloudflare — DNS (the one real gotcha)
- Cloudflare → hardpowerintel.com → DNS → add the records Vercel showed (apex A → the shown IP, or CNAME-flatten apex to `cname.vercel-dns.com`; `www` CNAME → `cname.vercel-dns.com`).
- **CRITICAL: set both records to "DNS only" (grey cloud), NOT proxied (orange).** Cloudflare's proxy breaks Vercel's automatic SSL issuance/verification; grey cloud lets Vercel terminate TLS directly.
- Back in Vercel, wait for "Valid Configuration" + SSL issued (usually minutes).

### 8.3 Supabase — Auth URL config (or magic links break)
- Supabase → Authentication → URL Configuration:
  - **Site URL** = `https://hardpowerintel.com`
  - **Redirect URLs** allowlist: add `https://hardpowerintel.com/**` and `https://www.hardpowerintel.com/**`. Keep the existing `*.vercel.app/**` during transition (harmless; remove later).
- Why: confirmation/magic-link emails use Site URL, and Supabase only honors redirects on the allowlist — without this, signup/login emails point to the old domain or are rejected.

### 8.4 Lemon Squeezy — nothing required for redirects
- The checkout return URL is passed per-checkout from the request origin (`product_options.redirect_url`), so it follows the domain automatically. The webhook stays `https://hpi-api.fly.dev/v1/webhooks/lemon-squeezy` (unchanged). Optional: update the store's cosmetic "website" field.

### 8.5 API CORS (precautionary)
- The web calls the API **server-side** (`apiFetch` is `server-only`), so browser-CORS likely doesn't apply. If any browser-side call ever hits the API directly, add the origin:
  `fly secrets set CORS_ALLOW_ORIGINS=https://hardpowerintel.com --app hpi-api`

### 8.6 Verify
- [ ] `https://hardpowerintel.com` loads with valid SSL (padlock).
- [ ] Fresh signup → the confirmation email link points to hardpowerintel.com and completes login.
- [ ] Checkout (test mode) → returns to `https://hardpowerintel.com/subscribe/success`.
- [ ] `/account` renders the correct tier.
