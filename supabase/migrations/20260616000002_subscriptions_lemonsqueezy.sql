-- Make `subscriptions` provider-correct for Lemon Squeezy and comp-compatible (D075).
-- The table was built for Stripe before the D050 switch to Lemon Squeezy. It is empty
-- (no subscription has ever succeeded — the webhook only logged), so this rename is
-- zero-data-risk.
--   * rename stripe_* → ls_* so the column names tell the truth
--   * drop NOT NULL on ls_customer_id: a COMPED user has no Lemon Squeezy customer
--     (UNIQUE stays — Postgres allows multiple NULLs)
--   * add `source` so paid vs comped subscribers are distinguishable and a webhook
--     can never clobber a comp by accident

ALTER TABLE subscriptions RENAME COLUMN stripe_customer_id TO ls_customer_id;
ALTER TABLE subscriptions RENAME COLUMN stripe_subscription_id TO ls_subscription_id;

ALTER TABLE subscriptions ALTER COLUMN ls_customer_id DROP NOT NULL;

ALTER TABLE subscriptions
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'lemonsqueezy'
        CHECK (source IN ('lemonsqueezy', 'comp'));

ALTER INDEX IF EXISTS subscriptions_stripe_customer RENAME TO subscriptions_ls_customer;
ALTER INDEX IF EXISTS subscriptions_stripe_subscription RENAME TO subscriptions_ls_subscription;
