-- D089: store the GDELT lead-theme volume series for the brief's Signal sparkline.
-- Nullable — NULL when nothing moved enough to flag or GDELT was unreachable. Like
-- `signal` (the prose line), this is aggregate media-attention color, never a cited
-- fact — kept out of the provable-claim path. Shape:
--   {"theme": str, "series": [float], "delta_pct": float|null, "direction": "up"|"down"|null}
ALTER TABLE briefs ADD COLUMN IF NOT EXISTS signal_series JSONB;
