-- Add the NRC (via Federal Register API) as a registered ingestion source (D095).
-- The Energy desk is consistently the thinnest (Phase B, 2026-06-19): the capital-flow
-- sources leave it starved of *regulatory* signal. The NRC is where the nuclear/SMR
-- convergence thesis becomes enforceable events (combined-license applications, advanced-
-- reactor rules, HALEU fuel decisions) ahead of the money or the 8-K. Pulled from the free,
-- no-key, public-domain Federal Register API filtered to the NRC agency.
-- The desk[] column is informational; the adapter tags each record's desk per probe at parse
-- time. fetch_cron mirrors the daily brief cadence (before the 09:00 UTC brief run).

INSERT INTO source_registry (id, name, adapter_class, desk, license_class, fetch_cron) VALUES
    ('nrc', 'U.S. Nuclear Regulatory Commission', 'NRCAdapter', '{"energy"}', 'public_domain', '0 7 * * *')
ON CONFLICT (id) DO NOTHING;
