from dataclasses import dataclass, field

_DEFAULT_SOURCE_WEIGHT = 0.6
_DEFAULT_ENTITY_IMPORTANCE = 0.5


def bucket_normalize(amount_usd: float | None) -> float:
    if not amount_usd:
        return 0.0
    if amount_usd < 10_000_000:
        return 0.2
    if amount_usd < 100_000_000:
        return 0.4
    if amount_usd < 1_000_000_000:
        return 0.7
    return 1.0


def minmax_normalize(value: float, min_val: float, max_val: float) -> float:
    if max_val == min_val:
        return 0.0
    return (value - min_val) / (max_val - min_val)


@dataclass
class MaterialityScorer:
    source_weights: dict[str, float]
    entity_importance: dict[str, float]
    materiality_threshold: float
    magnitude_min_window: int
    window_amounts: list[float] = field(default_factory=list)
    # Cross-sector convergence boost (D060): a record touching ≥2 desks is the
    # valuable signal, so multiply its base score by (1 + weight·(desks−1)), capped
    # at 2 extra desks. 0 disables it; single-desk records are unaffected.
    cross_sector_weight: float = 0.0

    def _magnitude(self, amount_usd: float | None) -> float:
        if amount_usd is None:
            return 0.0
        valid = [a for a in self.window_amounts if a is not None]
        if len(valid) >= self.magnitude_min_window:
            return minmax_normalize(amount_usd, min(valid), max(valid))
        return bucket_normalize(amount_usd)

    def _cross_sector_multiplier(self, desk_count: int) -> float:
        # 1 desk → 1.0; each extra desk adds `cross_sector_weight`, capped at +2 desks.
        extra = min(max(desk_count - 1, 0), 2)
        return 1.0 + self.cross_sector_weight * extra

    def score(
        self,
        source_id: str,
        is_new: bool,
        amount_usd: float | None,
        entity_type: str,
        corroboration_count: int,
        desk_count: int = 1,
    ) -> float:
        authority = self.source_weights.get(source_id, _DEFAULT_SOURCE_WEIGHT)
        novelty = 1.0 if is_new else 0.0
        magnitude = self._magnitude(amount_usd)
        importance = self.entity_importance.get(entity_type, _DEFAULT_ENTITY_IMPORTANCE)
        corroboration = min(corroboration_count, 3) / 3

        base = (
            authority * 0.25
            + novelty * 0.30
            + magnitude * 0.20
            + importance * 0.15
            + corroboration * 0.10
        )
        return min(base * self._cross_sector_multiplier(desk_count), 1.0)

    def is_material(self, score: float) -> bool:
        return score >= self.materiality_threshold
