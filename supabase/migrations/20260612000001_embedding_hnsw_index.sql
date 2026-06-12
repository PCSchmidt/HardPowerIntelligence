-- Replace the ivfflat embedding index with HNSW.
--
-- Root cause (found during the first production brief run): ivfflat with the default
-- `probes = 1` returns ZERO rows for an approximate-nearest-neighbor `ORDER BY
-- embedding <=> $vec` when the table holds very little data — the single probed list
-- is empty. The brief RAG retrieval (engine/brief/rag.py fetch_passages) JOINs
-- raw_records, which pushes the planner onto the ivfflat index, so it returned 0
-- passages on a freshly seeded DB. With no passages, the citation eval excluded every
-- item (faithfulness 0.000) and no brief could publish. (Confirmed: `SET ivfflat.probes
-- = 100` or forcing a seq scan both return the expected rows.)
--
-- HNSW has high recall out of the box (no probes tuning), is correct on small datasets,
-- and scales — the recommended pgvector index for this retrieval workload. The query
-- uses cosine distance (<=>), so the index uses vector_cosine_ops to match.

DROP INDEX IF EXISTS normalized_records_embedding;

CREATE INDEX normalized_records_embedding
    ON normalized_records
    USING hnsw (embedding vector_cosine_ops);
