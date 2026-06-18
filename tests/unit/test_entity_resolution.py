"""Resolver decision logic (T3.2, D091) — pure, no DB/LLM."""
from engine.entity.resolution import Candidate, decide
from engine.entity.resolver import ResolutionStatus


def _c(eid: str, name: str, sim: float) -> Candidate:
    return Candidate(entity_id=eid, canonical_name=name, similarity=sim)


class TestDecide:
    def test_empty_dismisses(self):
        r = decide([])
        assert r.status is ResolutionStatus.AUTO_DISMISS and r.entity_id is None

    def test_high_single_auto_links(self):
        r = decide([_c("e1", "LOCKHEED MARTIN", 0.99), _c("e2", "OTHER", 0.40)])
        assert r.status is ResolutionStatus.AUTO_LINK
        assert r.entity_id == "e1" and r.resolved_by == "auto_high_confidence"

    def test_ambiguous_high_tie_does_not_link(self):
        # two near-tied strong matches → record disambiguate, but DON'T link (precision-first)
        r = decide([_c("e1", "ACME CORP", 0.97), _c("e2", "ACME HOLDINGS", 0.95)])
        assert r.status is ResolutionStatus.LLM_DISAMBIGUATE and r.entity_id is None

    def test_clear_winner_over_weak_runner_up_links(self):
        r = decide([_c("e1", "ACME", 0.96), _c("e2", "ACME WIDGETS", 0.80)])
        assert r.status is ResolutionStatus.AUTO_LINK and r.entity_id == "e1"

    def test_medium_recorded_but_unresolved(self):
        r = decide([_c("e1", "SOMECO", 0.80)])
        assert r.status is ResolutionStatus.LLM_DISAMBIGUATE and r.entity_id is None

    def test_low_dismissed(self):
        r = decide([_c("e1", "X", 0.40)])
        assert r.status is ResolutionStatus.AUTO_DISMISS and r.entity_id is None
