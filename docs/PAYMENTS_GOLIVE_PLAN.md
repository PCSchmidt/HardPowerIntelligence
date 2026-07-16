# Payments go-live (C0) — plan

**Status:** SCOPED 2026-07-16 (not started). Flip Lemon Squeezy from TEST/dark to live + trial
mechanics. **Why it matters:** unblocks **B3** — the cold-cohort paid trial, the *only* clean read on
whether strangers will pay $19.99/mo (warm-cohort enthusiasm can't answer that). It's also the first
turn of the revenue→data flywheel: subscriptions fund paywalled sources → richer briefs/edges. See
[PHASE_PLAN.md](PHASE_PLAN.md), the `payments-revenue-loop` memory, [PERSONAS.md](PERSONAS.md).

---

## Current state (verified 2026-07-16) — this is config, not a build

The payment system is **built and tested**, and degrades gracefully while dark (same
scaffold-with-placeholder pattern as PostHog/Resend — the code is ready, the credentials aren't):

| Piece | State |
|---|---|
| Webhook handler | `api/app/routers/webhooks.py` — signature-verified, writes `subscriptions`. Tested (`tests/api/test_webhooks.py`). |
| Checkout | `web/app/api/checkout/route.ts` + `web/components/subscription/{pricing-table,checkout-button}.tsx` |
| Tier resolution | `api/app/deps.py:resolve_tier` — `tier='pro' AND status IN ('active','trialing')` → Pro. **Trialing already grants Pro.** |
| Comp path | `scripts/grant_comp.py` (source='comp', bypasses LS) — the warm-cohort lever, works today. |
| Graceful degrade | `web/lib/payments.ts:paymentsConfigured()` — reads LS env; **absent → "Pro coming soon"**, auto-flips on when env is set. No client flag to maintain (D088). |
| Config keys (unset) | API: `lemonsqueezy_api_key`, `_store_id`, `_webhook_secret`. Web: `LEMONSQUEEZY_API_KEY`, `_STORE_ID`, `_VARIANT_MONTHLY`/`_VARIANT_ANNUAL`. |

So C0 is **operator/config work**, not engineering. Lemon Squeezy is Merchant-of-Record (D050) — it
handles tax/VAT, which is why it was chosen over raw Stripe.

---

## §1 — Lemon Squeezy dashboard setup (operator)

1. Create/confirm the store. Note the **store ID**.
2. Create the product(s): a **Monthly** ($19.99) and optionally **Annual** subscription **variant**.
   Note each **variant ID** (the code keys off variant IDs, not product IDs).
3. Create an **API key** (Settings → API).
4. Create a **webhook** (Settings → Webhooks): URL = the API's webhook endpoint (the route in
   `api/app/routers/webhooks.py` — confirm the path, e.g. `https://<api-host>/webhooks/lemonsqueezy`),
   subscribe to `subscription_created` / `updated` / `cancelled` / `resumed` / `expired`. Note the
   **signing secret**.

## §2 — Wire credentials (operator; the load-bearing copies live in the hosts, not .env)

- **API (Fly)** — set `LEMONSQUEEZY_API_KEY`, `LEMONSQUEEZY_STORE_ID`, `LEMONSQUEEZY_WEBHOOK_SECRET`
  as Fly secrets, then `fly deploy --config fly.api.toml`.
- **Web (Vercel)** — set `LEMONSQUEEZY_API_KEY`, `LEMONSQUEEZY_STORE_ID`, `LEMONSQUEEZY_VARIANT_MONTHLY`
  (+ `_ANNUAL` if used) in Vercel → Environment Variables → **Production**, then redeploy.
  `paymentsConfigured()` flips the "coming soon" surfaces live automatically on the next build.

## §3 — End-to-end test (TEST mode first)

LS test mode → run a real checkout → confirm the webhook lands (signature verifies), a `subscriptions`
row is written with `tier='pro'`, `resolve_tier` returns `pro`, and the Pro surfaces (archive, etc.)
unlock for that account. This was verified once in TEST mode (D075); re-verify after the env wiring,
because the failure modes are all config (wrong variant ID, webhook URL unreachable from LS, signature
secret mismatch), and they fail silently — the D075 test proves the code, not this deployment's config.

## §4 — Trial mechanics (the B3 requirement)

B3 needs a **standard 30-day trial**. `resolve_tier` already treats `status='trialing'` as Pro, so the
lift is small: configure the LS subscription variant with a **free trial period**; LS then emits
`subscription_created` with a trialing status → the webhook writes `status='trialing'` → Pro for the
trial window → LS transitions to `active` (charges) or `expired` at trial end, and the webhook updates
the row. **Verify:** the trialing→active and trialing→expired transitions both map correctly (a trial
that silently stays Pro forever, or drops to free a day early, both corrupt the conversion read). Add a
webhook test for the trial transitions if not already covered.

## §5 — Flip live + smoke test

Switch LS to live mode, run one real (small) purchase end-to-end, confirm the row + tier + unlock, then
refund/cancel if it was just a smoke test. Watch the first real B3 trial signups land correctly.

---

## Effort & sequencing

Mostly **operator dashboard + env work** (hours, not gates), plus possibly a small webhook test for the
trial transitions (§4). No hero-surface dependency — runs fully in parallel with the convergence-graph
build. **This is the higher-leverage of the two parallel tracks for the *business* question:** it's the
gate on the only unbiased willingness-to-pay signal, and every day it's dark is a day of zero conversion
data. Recommend standing it up first (it's mostly config), then the graph build proceeds on its own clock.

**Related still-open:** the warm cohort (B2) runs on comps (`grant_comp.py`) and needs none of this —
so tester recruiting can start immediately; payments gate only the *cold, paid* read (B3).
