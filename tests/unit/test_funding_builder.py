"""Unit tests for federal-funding edge aggregation (Convergence-graph §5)."""
from engine.entity.funding_builder import aggregate_awards

UEI = {"AAA111": "ent-lockheed", "BBB222": "ent-nuscale"}


class TestAggregateAwards:
    def test_sums_dollars_and_counts_per_agency_recipient(self):
        records = [
            {"recipient_uei": "AAA111", "awarding_agency": "Department of Defense", "amount_usd": 1000, "start_date": "2026-06-01"},
            {"recipient_uei": "AAA111", "awarding_agency": "Department of Defense", "amount_usd": 500, "start_date": "2026-07-01"},
        ]
        agg = aggregate_awards(records, UEI)
        award = agg[("Department of Defense", "ent-lockheed")]
        assert award.total_usd == 1500
        assert award.award_count == 2
        assert award.last_award == "2026-07-01"  # most recent kept

    def test_splits_by_agency(self):
        records = [
            {"recipient_uei": "AAA111", "awarding_agency": "Department of Defense", "amount_usd": 100},
            {"recipient_uei": "AAA111", "awarding_agency": "Department of Energy", "amount_usd": 200},
        ]
        agg = aggregate_awards(records, UEI)
        assert set(agg.keys()) == {
            ("Department of Defense", "ent-lockheed"),
            ("Department of Energy", "ent-lockheed"),
        }

    def test_skips_unresolvable_recipient(self):
        records = [{"recipient_uei": "ZZZ999", "awarding_agency": "NASA", "amount_usd": 100}]
        assert aggregate_awards(records, UEI) == {}

    def test_skips_missing_agency(self):
        records = [{"recipient_uei": "AAA111", "amount_usd": 100}]
        assert aggregate_awards(records, UEI) == {}

    def test_uei_case_insensitive(self):
        records = [{"recipient_uei": "bbb222", "awarding_agency": "NSF", "amount_usd": 50}]
        agg = aggregate_awards(records, UEI)
        assert ("NSF", "ent-nuscale") in agg

    def test_non_numeric_amount_degrades_to_zero(self):
        records = [{"recipient_uei": "AAA111", "awarding_agency": "DoD", "amount_usd": None}]
        agg = aggregate_awards(records, UEI)
        assert agg[("DoD", "ent-lockheed")].total_usd == 0.0
        assert agg[("DoD", "ent-lockheed")].award_count == 1
