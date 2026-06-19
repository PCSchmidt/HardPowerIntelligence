-- GIN index on brief_items.entity_ids (T3.7, D091) — accelerates the `entity_ids @> ARRAY[id]`
-- containment used by the Entity 360 appearances query and the brief chip convergence aggregation.
-- IF NOT EXISTS keeps it idempotent for the CI migration-reconcile step (D090).
CREATE INDEX IF NOT EXISTS brief_items_entity_ids_gin ON brief_items USING GIN (entity_ids);
