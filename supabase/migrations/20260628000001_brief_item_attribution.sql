-- Epistemic attribution per brief item (D098/D099): the widen-the-net flip.
-- Grounding level is no longer a publish-suppression gate; it is a per-item confidence
-- LABEL. Each item is graded on one ordered ladder of decreasing certainty:
--   confirmed  → primary public record, claim citation-supported
--   reported   → attributed third-party reporting, not a primary record
--   analysis   → HPI synthesis/inference over the record(s)
--   speculative→ early/weak signal worth watching
-- See engine/engine/brief/epistemics.py (classify_item).
--
-- NOT NULL DEFAULT 'confirmed': every pre-D099 row is a cited-ledger item that was, by
-- the old publish gate, source-supported — i.e. confirmed — so the backfill default is
-- both safe and accurate.

ALTER TABLE brief_items
    ADD COLUMN IF NOT EXISTS attribution TEXT NOT NULL DEFAULT 'confirmed'
        CHECK (attribution IN ('confirmed', 'reported', 'analysis', 'speculative'));
