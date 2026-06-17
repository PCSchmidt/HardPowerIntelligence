-- D080: store the Lemon Squeezy customer-portal URL so /account can render a real
-- "Manage subscription" link. The signed URL arrives in every subscription_* webhook
-- (data.attributes.urls.customer_portal) and is refreshed on each update. Nullable:
-- comped subscribers (source='comp') have no Lemon Squeezy billing to manage.
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS customer_portal_url TEXT;
