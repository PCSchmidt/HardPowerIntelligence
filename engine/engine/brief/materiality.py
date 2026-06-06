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

    def _magnitude(self, amount_usd: float | None) -> float:
        if amount_usd is None:
            return 0.0
        valid = [a for a in self.window_amounts if a is not None]
        if len(valid) >= self.magnitude_min_window:
            return minmax_normalize(amount_usd, min(valid), max(valid))
        return bucket_normalize(amount_usd)

    def score(
        self,
        source_id: str,
        is_new: bool,
        amount_usd: float | None,
        entity_type: str,
        corroboration_count: int,
    ) -> float:
        authority = self.source_weights.get(source_id, _DEFAULT_SOURCE_WEIGHT)
        novelty = 1.0 if is_new else 0.0
        magnitude = self._magnitude(amount_usd)
        importance = self.entity_importance.get(entity_type, _DEFAULT_ENTITY_IMPORTANCE)
        corroboration = min(corroboration_count, 3) / 3

        return (
            authority * 0.25
            + novelty * 0.30
            + magnitude * 0.20
            + importance * 0.15
            + corroboration * 0.10
        )

    def is_material(self, score: float) -> bool:
        return score >= self.materiality_threshold
