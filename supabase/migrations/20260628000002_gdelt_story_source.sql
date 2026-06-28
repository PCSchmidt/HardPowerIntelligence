-- Activate GDELT as a story source (D101). The initial schema seeded a placeholder
-- 'gdelt' row (adapter_class 'GDELTAdapter', license 'public_domain', */15 cron) for an
-- adapter that was never built. Now that GDELTAdapter exists, correct the row:
--   * license_class → scrape_gray: GDELT indexes third-party news; we store/cite the
--     TITLE and link only, never article body text (the epistemic flip D098/D099 lets
--     these in as labeled Speculative, link-only stories — never a republished feed).
--   * fetch_cron → daily, aligned to the brief run (the */15 real-time cadence was the
--     superseded design; D055 fixed daily).
--   * desk → all three: GDELT probes are tagged per home desk at parse time; this column
--     is informational.
-- Idempotent: also INSERT if the placeholder row is absent on a given DB.

INSERT INTO source_registry (id, name, adapter_class, desk, license_class, fetch_cron) VALUES
    ('gdelt', 'GDELT (worldwide news)', 'GDELTAdapter',
     '{"defense","ai","energy"}', 'scrape_gray', '0 6 * * *')
ON CONFLICT (id) DO UPDATE SET
    name          = EXCLUDED.name,
    adapter_class = EXCLUDED.adapter_class,
    desk          = EXCLUDED.desk,
    license_class = EXCLUDED.license_class,
    fetch_cron    = EXCLUDED.fetch_cron,
    is_active     = true;
