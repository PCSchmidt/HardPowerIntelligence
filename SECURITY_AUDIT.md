# Security Audit — Hard Power Intelligence (Gate 8)

Date: 2026-06-11 · Scope: `api/`, `engine/`, `worker/`, `web/`, `supabase/` ·
Method: OWASP Top 10 + AI-specific threats (Blueprint `/security`).

**Verdict: PASS (advisory).** 0 Critical, 0 High, 1 Medium, 2 Low, plus deploy-config
items to confirm at Gate 9. No autonomous fixes were required (none Critical/High).

---

## OWASP Top 10

### A01 — Broken Access Control
- ✅ Every data endpoint declares `Depends(get_principal)` (briefs list/latest/by-id,
  calendar, auth/me). Auth-exempt routes (`/health`, webhook) intentionally omit it.
- ✅ RLS enabled on all user/intelligence tables. User tables are own-row
  (`auth.uid()`); `subscriptions` is client read-only (server-writes only); ingestion
  tables (`raw_records`, `normalized_records`, `resolution_queue`) are deny-all
  (`USING (false)`, service role bypasses).
- 🟡 **MEDIUM — briefs paywall is bypassable at the data layer.** `briefs`,
  `brief_items`, `citations`, `entities`, `entity_edges` grant `SELECT TO authenticated
  USING (true / status='published')`, and migrations add no `REVOKE`, so Supabase's
  default PostgREST grants stand. The app reads briefs only through FastAPI
  (`FASTAPI_INTERNAL_URL`, D011), where the Pro/archive paywall (D012) lives — but a
  logged-in **free** user can call Supabase PostgREST directly with their JWT + the
  public anon key and read the **entire published archive**, bypassing the Pro gate.
  Impact: subscription-revenue leakage, not a PII/cross-user breach.
  **Fix (recommended):** new migration revoking `authenticated` SELECT on
  `briefs/brief_items/citations/entities/entity_edges` so all reads go through the
  FastAPI service role (consistent with D011's "single data boundary"). Alternative:
  tier-aware RLS (free = briefs newer than N days; Pro = full archive).

### A02 — Cryptographic Failures
- ✅ No secrets in source; no `.env*` tracked or in git history.
- ✅ JWT verified via Supabase JWKS (ES/RS/PS) or HS256 shared secret; `aud` checked.
- 🔧 Deploy-config (Gate 9): JWT secret ≥ 32 chars (Supabase provides), HTTPS enforced
  (Vercel + Supabase default).

### A03 — Injection
- ✅ All SQL parameterized (`$1` placeholders, `uuid.UUID()` coercion); no f-string SQL.
- ✅ No `eval`/`exec`/`subprocess`/`shell=True`. Inputs validated via Pydantic v2.

### A05 — Security Misconfiguration
- ✅ CORS origins come from env (`cors_allow_origins`), no wildcard with credentials.
- 🔧 Deploy-config (Gate 9): set `ENVIRONMENT=production` and the real `CORS_ALLOW_ORIGINS`;
  consider disabling FastAPI `/docs` in production.

### A07 — Identification & Authentication Failures
- ✅ JWT verification on all protected endpoints; expiry enforced by PyJWT default.
- 🟢 **LOW — JWT `alg` is read from the unverified header** to pick the verification
  path. Mitigated (HS256 path uses the shared secret; asymmetric path uses JWKS public
  keys, so algorithm-confusion forgery needs the secret), but pinning the expected
  algorithm(s) per environment would be more robust.

## AI-Specific
- ✅ **Cost ceiling:** structurally bounded — briefs are generated once per desk per
  cadence and shared (D003); there is no per-user LLM generation path in Cycle 1, so a
  user cannot drive LLM spend. Per-user cost ceiling is N/A this cycle.
- ✅ **Prompt injection:** brief inputs are government data, not subscriber free-text;
  no user input is placed in a system prompt. Output passes the citation-faithfulness
  eval gate (Gate 5).
- 🟢 **LOW — adversarial ingested content:** ingested source text is untrusted and
  flows into synthesis prompts. Low risk today (no tool-use, output is citation-checked),
  but worth revisiting when user-facing query features arrive (Cycle 2).

## Webhook (Lemon Squeezy, D050)
- ✅ HMAC-SHA256 verified with constant-time `hmac.compare_digest`.
- 🔧 Launch blocker: `LEMONSQUEEZY_WEBHOOK_SECRET` is unset, so the handler degrades to
  accept-and-ignore (D045). Must be configured before payments go live.

---

## Action items
| Sev | Item | When |
|-----|------|------|
| MEDIUM | ✅ FIXED + VERIFIED on cloud (2026-06-12) — `20260611000001_lock_briefs_rls.sql` applied; `authenticated`/`anon` confirmed to have no SELECT on briefs/citations/entities | Done |
| LOW | Pin expected JWT alg(s) per environment | Cycle 2 / hardening |
| LOW | Re-evaluate adversarial ingested-content handling when user queries ship | Cycle 2 |
| CONFIG | ✅ `ENVIRONMENT=production` + real `CORS_ALLOW_ORIGINS` set on Fly (2026-06-12). ⬜ Still: Lemon Squeezy webhook secret, optional `/docs` disable | Partial |
