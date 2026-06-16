-- Layered brief fields (D071/D073): persist the analysis layer alongside the cited facts.
-- Each item gains a `read` (why it's material — analysis) and an optional `watch` (forward
-- catalyst); the brief gains a `convergence_read` (cross-desk thesis). These are ANALYSIS,
-- not cited claims: they are held to grounding, not per-sentence citation (D071), and only
-- grounded text is stored (regenerate-then-omit, D073) — so an empty string means the
-- analysis was withheld, never that a fabrication leaked through.
-- NOT NULL DEFAULT '' so existing rows (cited-ledger briefs) remain valid.

ALTER TABLE brief_items
    ADD COLUMN IF NOT EXISTS read  TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS watch TEXT NOT NULL DEFAULT '';

ALTER TABLE briefs
    ADD COLUMN IF NOT EXISTS convergence_read TEXT NOT NULL DEFAULT '';
