-- Add arXiv as a registered ingestion source (D066).
-- arXiv is the technology-advancement leg of a brief (D063): a leading indicator
-- of where capability is moving, feeding the AI desk (starved by the capital-flow
-- sources) plus Defense∩AI (autonomy) and AI∩Energy (grid/fusion ML) convergence.
-- The desk[] column here is informational; the adapter tags each record's desk(s)
-- per probe at parse time. fetch_cron mirrors the daily brief cadence.

INSERT INTO source_registry (id, name, adapter_class, desk, license_class, fetch_cron) VALUES
    ('arxiv', 'arXiv', 'ArxivAdapter', '{"ai","defense","energy"}', 'public_domain', '0 7 * * *')
ON CONFLICT (id) DO NOTHING;
