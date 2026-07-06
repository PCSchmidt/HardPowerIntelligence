-- Source publication date on citations (D129).
--
-- The reader showed only `fetched_at` — WHEN WE RETRIEVED a source, which for a daily pipeline is
-- always ~today. So a two-year-old article and this-morning's news looked equally fresh, hiding
-- staleness. Persist the SOURCE's own publication/action date (parsed from structured_data at
-- assemble time by engine.brief.rag.extract_published_at) so the reader can show "Published <date>"
-- and the user can judge how stale, if at all, the underlying information is.
--
-- NULLABLE on purpose: many records have no reliable publication date (or an unparseable one).
-- Those are NOT dropped — the reader degrades to the retrieval date with a "Retrieved" label
-- (operator directive: don't drop data that has no publication date).

ALTER TABLE citations
    ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;
