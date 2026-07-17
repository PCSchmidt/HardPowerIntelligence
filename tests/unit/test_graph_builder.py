"""Unit tests for convergence-edge computation (Convergence-graph §1).

Locks the weighting / recency-decay / cross-desk-boost / prune-floor math that decides whether the
graph compounds signal or noise. Expected values are hand-computed from the spec (0.5**(age/half_life)
decay, cross-desk 2× boost, weight floor), NOT read off the implementation — so these assert the
contract, not the code. The DB layer (fetch/persist/upsert) is exercised by the operator run.
"""
from datetime import date

import pytest

from engine.entity.graph_builder import (
    CoAppearance,
    canonical_pair,
    compute_edges,
    confidence_from_weight,
    pairs_from_item,
    recency_weight,
    same_company,
)

NOW = date(2026, 7, 16)
# Standard knobs for the aggregate tests (match settings defaults).
KW = dict(now=NOW, half_life_days=30.0, weight_floor=1.5, cross_desk_boost=2.0)


class TestCanonicalPair:
    def test_orders_by_text(self):
        assert canonical_pair("b", "a") == ("a", "b")
        assert canonical_pair("a", "b") == ("a", "b")


class TestRecencyWeight:
    def test_age_zero_is_full(self):
        assert recency_weight(0, 30) == 1.0

    def test_one_half_life_halves(self):
        assert recency_weight(30, 30) == 0.5

    def test_two_half_lives_quarters(self):
        assert recency_weight(60, 30) == 0.25

    def test_negative_age_clamped(self):
        assert recency_weight(-5, 30) == 1.0

    def test_nonpositive_half_life_guarded(self):
        assert recency_weight(10, 0) == 1.0


class TestConfidenceFromWeight:
    def test_known_points(self):
        assert confidence_from_weight(0) == 0.0
        assert confidence_from_weight(1) == 0.5
        assert confidence_from_weight(2) == 0.75
        assert confidence_from_weight(3) == 0.875


class TestPairsFromItem:
    def test_three_entities_make_three_pairs(self):
        pairs = list(pairs_from_item(["x", "y", "z"], "defense", NOW))
        assert {(p.a, p.b) for p in pairs} == {("x", "y"), ("x", "z"), ("y", "z")}

    def test_duplicates_collapsed(self):
        pairs = list(pairs_from_item(["x", "x", "y"], "energy", NOW))
        assert [(p.a, p.b) for p in pairs] == [("x", "y")]

    def test_single_entity_no_pairs(self):
        assert list(pairs_from_item(["x"], "ai", NOW)) == []


class TestSameCompany:
    def test_prefix_variant_is_same_company(self):
        # the live Northrop artifact: parent vs division/legal variant
        assert same_company("Northrop Grumman Corp /DE/", "NORTHROP GRUMMAN SYSTEMS CORPORATION")

    def test_identical_after_suffix_normalization(self):
        assert same_company("Palantir Technologies Inc.", "Palantir Technologies Corp")

    def test_distinct_companies_sharing_one_token_are_not_merged(self):
        assert not same_company("General Dynamics", "General Electric")
        assert not same_company("Rare Earths Americas", "USA Rare Earth")

    def test_single_shared_token_never_merges(self):
        # "Energy" alone must not merge two different energy companies
        assert not same_company("Energy Fuels", "Energy Transfer")

    def test_blank_names_are_not_same(self):
        assert not same_company("", "Anything")
        assert not same_company("Boeing", "")


class TestComputeEdges:
    def test_same_desk_single_recent_is_pruned(self):
        # raw weight 1.0 (age 0), same desk → no boost → 1.0 < floor 1.5 → coincidence, dropped.
        obs = [CoAppearance("a", "b", "defense", NOW)]
        assert compute_edges(obs, **KW) == []

    def test_same_desk_repeated_is_kept(self):
        # two recent co-appearances, same desk → raw 2.0 ≥ 1.5. confidence 1-0.5**2 = 0.75.
        obs = [CoAppearance("a", "b", "defense", NOW), CoAppearance("a", "b", "defense", NOW)]
        edges = compute_edges(obs, **KW)
        assert len(edges) == 1
        e = edges[0]
        assert (e.from_id, e.to_id) == ("a", "b")
        assert e.co_count == 2
        assert e.cross_desk is False
        assert e.desks == ("defense",)
        assert e.weight == pytest.approx(2.0)
        assert e.confidence == pytest.approx(0.75)

    def test_cross_desk_boost_rescues_a_weak_pair(self):
        # defense age 0 (1.0) + energy age 60 (0.25) → raw 1.25 (< 1.5, would prune) → ×2 boost = 2.5.
        obs = [
            CoAppearance("a", "b", "defense", NOW),
            CoAppearance("a", "b", "energy", date(2026, 5, 17)),  # 60 days before NOW
        ]
        edges = compute_edges(obs, **KW)
        assert len(edges) == 1
        e = edges[0]
        assert e.cross_desk is True
        assert e.desks == ("defense", "energy")
        assert e.co_count == 2
        assert e.weight == pytest.approx(2.5)
        assert e.confidence == pytest.approx(1 - 0.5 ** 2.5)  # ≈ 0.823223

    def test_stale_convergence_decays_below_floor(self):
        # two co-appearances both 60 days old, same desk → raw 0.5 → pruned. Time removes dead signal.
        old = date(2026, 5, 17)
        obs = [CoAppearance("a", "b", "energy", old), CoAppearance("a", "b", "energy", old)]
        assert compute_edges(obs, **KW) == []

    def test_self_pairs_ignored(self):
        obs = [CoAppearance("a", "a", "defense", NOW), CoAppearance("a", "a", "defense", NOW)]
        assert compute_edges(obs, **KW) == []

    def test_reversed_pairs_aggregate_canonically(self):
        # (b,a) and (a,b) are the same undirected pair across two desks → one cross-desk edge.
        obs = [CoAppearance("a", "b", "defense", NOW), CoAppearance("b", "a", "energy", NOW)]
        edges = compute_edges(obs, **KW)
        assert len(edges) == 1
        e = edges[0]
        assert (e.from_id, e.to_id) == ("a", "b")
        assert e.co_count == 2
        assert e.cross_desk is True

    def test_sorted_strongest_first(self):
        # Pair (a,b) cross-desk (strong) vs (c,d) same-desk repeated (weaker) → strong first.
        obs = [
            CoAppearance("a", "b", "defense", NOW),
            CoAppearance("a", "b", "energy", NOW),   # cross-desk: raw 2.0 ×2 = 4.0
            CoAppearance("c", "d", "ai", NOW),
            CoAppearance("c", "d", "ai", NOW),        # same-desk: raw 2.0
        ]
        edges = compute_edges(obs, **KW)
        assert [(e.from_id, e.to_id) for e in edges] == [("a", "b"), ("c", "d")]
        assert edges[0].weight > edges[1].weight

    def test_last_seen_is_most_recent(self):
        obs = [
            CoAppearance("a", "b", "defense", date(2026, 7, 1)),
            CoAppearance("a", "b", "defense", NOW),
        ]
        edges = compute_edges(obs, **KW)
        assert edges[0].last_seen == NOW
