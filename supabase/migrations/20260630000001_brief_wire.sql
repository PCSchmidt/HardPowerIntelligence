-- "Full Wire" overflow capture (D112): material, on-thesis items that cleared the
-- materiality threshold and home-desk routing but lost the brief's space cut (the
-- synthesis fact-selection cap / item ceiling). They were previously discarded.
--
-- Persist them here so a per-desk /wire page can surface them — title + source + link,
-- no narrative — so a heavy news day doesn't throw away real signal ("don't throw the
-- baby out with the bathwater", operator 2026-06-30). One row per dropped material
-- candidate, tied to its brief; cascades away when the brief is replaced.
--
-- "Material overflow only": froth the significance gate (D085) rejected is excluded, and
-- items featured in the published brief are excluded (those are already on the desk page).
CREATE TABLE brief_wire (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brief_id          UUID NOT NULL REFERENCES briefs(id) ON DELETE CASCADE,
    source_id         TEXT NOT NULL,
    native_id         TEXT,
    item_type         TEXT,
    headline          TEXT NOT NULL,
    url               TEXT,
    materiality_score FLOAT,
    display_order     INT NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX brief_wire_brief_id ON brief_wire (brief_id, display_order);

-- Same posture as briefs/brief_items (D011, lock_briefs_rls): the wire is read ONLY
-- through the FastAPI data boundary, whose asyncpg/DATABASE_URL role bypasses RLS. Deny
-- all PostgREST (anon/authenticated) clients — enable RLS with no permissive policy and
-- revoke the default grants. The /wire API endpoint itself is public (no tier gate).
ALTER TABLE brief_wire ENABLE ROW LEVEL SECURITY;
REVOKE SELECT ON brief_wire FROM anon, authenticated;
