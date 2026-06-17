-- D082: store the labeled GDELT media-attention "Signal" line on the brief. Nullable/
-- empty when nothing moved enough to flag. This is aggregate momentum color, never a
-- cited fact — kept in its own column so it stays out of the provable-claim path.
ALTER TABLE briefs ADD COLUMN IF NOT EXISTS signal TEXT NOT NULL DEFAULT '';
