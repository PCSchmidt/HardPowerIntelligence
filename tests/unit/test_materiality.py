"""
Tests for engine/brief/materiality.py (D030, D035, D036).
Pure unit tests — no DB, no network.
"""
from engine.brief.materiality import (
    MaterialityScorer,
    bucket_normalize,
    minmax_normalize,
)


class TestBucketNormalize:
    def test_none_returns_zero(self):
        assert bucket_normalize(None) == 0.0

    def test_zero_returns_zero(self):
        assert bucket_normalize(0) == 0.0

    def test_under_10m(self):
        assert bucket_normalize(5_000_000) == 0.2

    def test_exactly_10m(self):
        assert bucket_normalize(10_000_000) == 0.4

    def test_between_10m_and_100m(self):
        assert bucket_normalize(50_000_000) == 0.4

    def test_exactly_100m(self):
        assert bucket_normalize(100_000_000) == 0.7

    def test_between_100m_and_1b(self):
        assert bucket_normalize(500_000_000) == 0.7

    def test_exactly_1b(self):
        assert bucket_normalize(1_000_000_000) == 1.0

    def test_over_1b(self):
        assert bucket_normalize(5_000_000_000) == 1.0


class TestMinmaxNormalize:
    def test_at_maximum_returns_one(self):
        assert minmax_normalize(1_000_000_000, min_val=0, max_val=1_000_000_000) == 1.0

    def test_at_minimum_returns_zero(self):
        assert minmax_normalize(0, min_val=0, max_val=1_000_000_000) == 0.0

    def test_at_midpoint(self):
        result = minmax_normalize(500_000_000, min_val=0, max_val=1_000_000_000)
        assert abs(result - 0.5) < 0.001

    def test_zero_range_returns_zero(self):
        assert minmax_normalize(100, min_val=100, max_val=100) == 0.0


class TestMaterialityScorer:
    def _scorer(self, window_amounts=None):
        source_weights = {"usaspending": 0.9, "gdelt": 0.5}
        entity_importance = {"company": 1.0, "sector": 0.5}
        return MaterialityScorer(
            source_weights=source_weights,
            entity_importance=entity_importance,
            materiality_threshold=0.35,
            magnitude_min_window=3,
            window_amounts=window_amounts or [],
        )

    def test_high_materiality_usaspending_award(self):
        scorer = self._scorer()
        score = scorer.score(
            source_id="usaspending",
            is_new=True,
            amount_usd=1_100_000_000,
            entity_type="company",
            corroboration_count=2,
        )
        assert score > 0.35

    def test_low_materiality_old_gdelt(self):
        scorer = self._scorer()
        score = scorer.score(
            source_id="gdelt",
            is_new=False,
            amount_usd=None,
            entity_type="sector",
            corroboration_count=0,
        )
        assert score < 0.35

    def test_novelty_binary_impact(self):
        scorer = self._scorer()
        new_score = scorer.score("usaspending", True, 500_000_000, "company", 0)
        old_score = scorer.score("usaspending", False, 500_000_000, "company", 0)
        # Novelty is 0.20 weight (rebalanced 2026-06-30) — new still materially higher
        assert new_score > old_score
        assert abs(new_score - old_score) > 0.15

    def test_corroboration_capped_at_3(self):
        scorer = self._scorer()
        score_3 = scorer.score("usaspending", True, 100_000_000, "company", 3)
        score_10 = scorer.score("usaspending", True, 100_000_000, "company", 10)
        assert score_3 == score_10

    def test_score_between_zero_and_one(self):
        scorer = self._scorer()
        score = scorer.score("usaspending", True, 1_000_000_000, "company", 3)
        assert 0.0 <= score <= 1.0

    def test_unknown_source_uses_default_weight(self):
        scorer = self._scorer()
        # Should not raise for unknown source_id
        score = scorer.score("unknown_source", True, 100_000_000, "company", 1)
        assert 0.0 <= score <= 1.0

    def test_unknown_entity_type_uses_default_importance(self):
        scorer = self._scorer()
        score = scorer.score("usaspending", True, 100_000_000, "unknown_type", 1)
        assert 0.0 <= score <= 1.0

    def test_minmax_used_when_window_large_enough(self):
        amounts = [10_000_000, 100_000_000, 500_000_000, 1_000_000_000]
        scorer = self._scorer(window_amounts=amounts)
        # 1B is max in window → magnitude = 1.0 → higher than bucket
        score_mm = scorer.score("usaspending", True, 1_000_000_000, "company", 0)
        scorer_empty = self._scorer(window_amounts=[])
        score_bucket = scorer_empty.score("usaspending", True, 1_000_000_000, "company", 0)
        # Both should be close (1B hits 1.0 in both paths)
        assert abs(score_mm - score_bucket) < 0.05

    def test_is_above_threshold(self):
        scorer = self._scorer()
        score = scorer.score("usaspending", True, 1_100_000_000, "company", 2)
        assert scorer.is_material(score)

    def test_is_below_threshold(self):
        scorer = self._scorer()
        score = scorer.score("gdelt", False, None, "sector", 0)
        assert not scorer.is_material(score)


class TestCrossSectorBoost:
    """Convergence boost (D060): records touching ≥2 desks score higher."""

    def _scorer(self, weight=0.15):
        return MaterialityScorer(
            source_weights={"edgar": 0.85},
            entity_importance={"company": 1.0},
            materiality_threshold=0.35,
            magnitude_min_window=3,
            window_amounts=[],
            cross_sector_weight=weight,
        )

    def test_single_desk_unaffected(self):
        # Default weight 0.0 and default desk_count=1 → identical to old behavior.
        plain = MaterialityScorer(
            source_weights={"edgar": 0.85}, entity_importance={"company": 1.0},
            materiality_threshold=0.35, magnitude_min_window=3, window_amounts=[],
        )
        boosted = self._scorer()
        args = dict(source_id="edgar", is_new=True, amount_usd=None,
                    entity_type="company", corroboration_count=0)
        assert plain.score(**args) == boosted.score(**args, desk_count=1)

    def test_two_desks_beats_one(self):
        scorer = self._scorer()
        args = dict(source_id="edgar", is_new=True, amount_usd=None,
                    entity_type="company", corroboration_count=0)
        assert scorer.score(**args, desk_count=2) > scorer.score(**args, desk_count=1)

    def test_three_desks_beats_two(self):
        scorer = self._scorer()
        args = dict(source_id="edgar", is_new=True, amount_usd=None,
                    entity_type="company", corroboration_count=0)
        assert scorer.score(**args, desk_count=3) > scorer.score(**args, desk_count=2)

    def test_boost_caps_at_three_desks(self):
        scorer = self._scorer()
        args = dict(source_id="edgar", is_new=True, amount_usd=None,
                    entity_type="company", corroboration_count=0)
        # 4th desk can't happen, but the multiplier must not keep growing.
        assert scorer.score(**args, desk_count=4) == scorer.score(**args, desk_count=3)

    def test_score_still_capped_at_one(self):
        scorer = self._scorer(weight=0.5)
        score = scorer.score("edgar", True, 1_000_000_000, "company", 3, desk_count=3)
        assert score <= 1.0

    def test_convergence_can_lift_over_threshold(self):
        # A modest single-desk item below threshold can clear it as a convergence item.
        scorer = self._scorer(weight=0.30)
        args = dict(source_id="edgar", is_new=False, amount_usd=20_000_000,
                    entity_type="company", corroboration_count=0)
        one = scorer.score(**args, desk_count=1)
        three = scorer.score(**args, desk_count=3)
        assert three > one
