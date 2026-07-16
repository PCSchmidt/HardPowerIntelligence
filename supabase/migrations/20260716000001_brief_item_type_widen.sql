-- Widen brief_items.item_type beyond the EDGAR-era taxonomy (D143).
--
-- The original CHECK (award|filing|policy|macro|signal) was written 2026-06-05 when the corpus
-- was SEC filings + gov awards. The net has since widened to news, arXiv, and agency feeds, so
-- the synthesis model routinely reaches for labels outside the five — and D140 had to coerce them
-- all to "signal" to keep persist from throwing. The cost of that safety net: on 2026-07-15 the
-- Defense desk persisted 10 of 20 items as "signal", including the lead story (first combat use of
-- unmanned surface vessels), flattening two genuinely distinct kinds of item — real-world military
-- OPERATIONS and RESEARCH / technology milestones — into the catch-all.
--
-- This adds those two as first-class types. Purely ADDITIVE and backward-compatible: every existing
-- row already satisfies the wider set, so no data migration is needed. Must land BEFORE the engine
-- begins emitting the new types (the inverse of the D140 failure — an unmigrated value would throw
-- CheckViolationError and take the desk dark), and the web must map them before any brief carries
-- them (an unmapped ItemType renders `undefined`). Deploy order: this migration → web → engine.

ALTER TABLE brief_items DROP CONSTRAINT brief_items_item_type_check;

ALTER TABLE brief_items ADD CONSTRAINT brief_items_item_type_check CHECK (
    item_type IN ('award', 'filing', 'policy', 'macro', 'signal', 'operational', 'research')
);
