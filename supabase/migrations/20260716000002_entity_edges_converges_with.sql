-- Add CONVERGES_WITH to entity_edges.edge_type + a partial unique index for idempotent upsert
-- (Convergence-graph §1, 2026-07-16).
--
-- entity_edges shipped 2026-06-05 with 15 SEMANTIC relationship types (AWARDED, SUPPLIES,
-- COMPETES_WITH, EXPOSED_TO, …) and NO co-occurrence type — the original design envisioned a true
-- relationship knowledge graph. The Convergence Map, however, renders CO-APPEARANCE: "these two
-- entities keep showing up together across desks," which is literally the cross-sector thesis and is
-- computable now from brief_items.entity_ids. That is a weakly-semantic, symmetric edge that fits
-- none of the 15 types, so this adds a distinct CONVERGES_WITH type rather than overloading a
-- semantic one (keeps the node-detail semantic edges, §5, cleanly separable). Purely ADDITIVE:
-- entity_edges has 0 rows today, so no data migration.
--
-- CONVERGES_WITH is UNDIRECTED; the edge job stores it canonically (from_entity_id < to_entity_id as
-- text) so a pair is one row, not two. The partial unique index below (a) enforces that one-row
-- invariant among LIVE edges and (b) gives the recompute job an ON CONFLICT target so it can upsert
-- weight/confidence/properties in place as briefs accrue — idempotent, mirroring the linker's
-- best-effort recompute pattern. Retired edges (valid_to set when a pair drops below the prune floor)
-- keep their bitemporal history and are excluded from the index, so the invariant is "one live edge
-- per canonical pair per type," not "ever."

ALTER TABLE entity_edges DROP CONSTRAINT entity_edges_edge_type_check;

ALTER TABLE entity_edges ADD CONSTRAINT entity_edges_edge_type_check CHECK (
    edge_type IN (
        'HAS_SECURITY', 'FILES_AS', 'REGISTERED_AS',
        'PARENT_OF', 'RUNS_PROGRAM', 'AWARDED',
        'SUPPLIES', 'COMPETES_WITH', 'INSIDER_OF',
        'TRANSACTED', 'HOLDS', 'MEMBER_OF',
        'PRODUCES', 'EXPOSED_TO', 'OPERATES',
        'CONVERGES_WITH'
    )
);

CREATE UNIQUE INDEX entity_edges_live_pair
    ON entity_edges (from_entity_id, to_entity_id, edge_type)
    WHERE valid_to IS NULL;
