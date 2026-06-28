-- Register the generic RSS/Atom feed source (D104) — the scale lever for breadth.
-- One adapter (FeedsAdapter) ingests a registry of named outlets (trade press, think
-- tanks, company IR) as the `reported` confidence tier (a configured, named outlet is
-- attributed reporting), license_class `scrape_gray` (title + link + short snippet only).
-- The desk[] column is informational; each feed tags its home desk at parse time.
-- Daily cron, aligned to the brief run.

INSERT INTO source_registry (id, name, adapter_class, desk, license_class, fetch_cron) VALUES
    ('feeds', 'Curated RSS/Atom feeds (trade press, think tanks, IR)', 'FeedsAdapter',
     '{"defense","ai","energy"}', 'scrape_gray', '0 6 * * *')
ON CONFLICT (id) DO UPDATE SET
    name          = EXCLUDED.name,
    adapter_class = EXCLUDED.adapter_class,
    desk          = EXCLUDED.desk,
    license_class = EXCLUDED.license_class,
    fetch_cron    = EXCLUDED.fetch_cron,
    is_active     = true;
