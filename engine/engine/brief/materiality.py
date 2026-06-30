from dataclasses import dataclass, field

_DEFAULT_SOURCE_WEIGHT = 0.6
_DEFAULT_ENTITY_IMPORTANCE = 0.5


def bucket_normalize(amount_usd: float | None) -> float:
    if not amount_usd:
        return 0.0
    # Sub-$10M awards used to share one flat 0.2 floor, so a $1.6M grant scored the same
    # as a $9M one and could lead a desk over deeper signal (operator review, 2026-06-30).
    # Split the floor so genuinely small grants sink while mid-size ones keep some weight.
    if amount_usd < 1_000_000:
        return 0.05
    if amount_usd < 5_000_000:
        return 0.15
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
    # Cross-sector convergence boost (D060, made ADDITIVE 2026-06-30): a record touching
    # ≥2 desks is the valuable signal, so it gets a small fixed bonus per extra desk
    # (capped at +2 desks). Additive, NOT multiplicative: a multiplicative boost scaled
    # with the base score and let a small 3-desk grant overpower a 20×-larger single-desk
    # award on its home desk (operator review). As an additive tiebreak it lifts a
    # convergence item above an otherwise-equal single-desk one without inverting
    # magnitude. 0 disables it; single-desk records are unaffected.
    cross_sector_weight: float = 0.0

    def _magnitude(self, amount_usd: float | None) -> float:
        if amount_usd is None:
            return 0.0
        valid = [a for a in self.window_amounts if a is not None]
        if len(valid) >= self.magnitude_min_window:
            return minmax_normalize(amount_usd, min(valid), max(valid))
        return bucket_normalize(amount_usd)

    def _cross_sector_bonus(self, desk_count: int) -> float:
        # 1 desk → +0; each extra desk adds `cross_sector_weight`, capped at +2 desks.
        extra = min(max(desk_count - 1, 0), 2)
        return self.cross_sector_weight * extra

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

        # Weights rebalanced 2026-06-30 (operator review): every same-day candidate is
        # is_new=True, so flat novelty (was 0.30) can't rank items against each other — it
        # was dead weight that let small fresh grants tie deeper signal. Trimmed into
        # authority + magnitude so confirmed-tier sources and larger awards lead. Magnitude
        # is 0 for no-dollar items (news/research), so the lift to authority keeps those
        # signals competitive rather than burying them under awards.
        base = (
            authority * 0.30
            + novelty * 0.20
            + magnitude * 0.25
            + importance * 0.15
            + corroboration * 0.10
        )
        return min(base + self._cross_sector_bonus(desk_count), 1.0)

    def is_material(self, score: float) -> bool:
        return score >= self.materiality_threshold
