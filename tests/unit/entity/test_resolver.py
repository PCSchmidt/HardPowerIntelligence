"""
Tests for the entity resolver cascade (D027).
All tests are pure unit tests — no DB, no LLM calls.
Gate 4 acceptance: these tests must pass.
"""

import pytest

from engine.entity.resolver import (
    ResolutionResult,
    ResolutionStatus,
    normalize_mention,
    score_candidate,
    triage,
)


class TestNormalizeMention:
    def test_uppercases(self):
        assert normalize_mention("Lockheed Martin") == "LOCKHEED MARTIN"

    def test_strips_whitespace(self):
        assert normalize_mention("  Raytheon  ") == "RAYTHEON"

    def test_removes_inc_suffix(self):
        assert normalize_mention("Boeing Inc") == "BOEING"

    def test_removes_corp_suffix(self):
        assert normalize_mention("General Dynamics Corp") == "GENERAL DYNAMICS"

    def test_removes_corporation_suffix(self):
        assert normalize_mention("Northrop Grumman Corporation") == "NORTHROP GRUMMAN"

    def test_removes_llc_suffix(self):
        assert normalize_mention("L3Harris Technologies LLC") == "L3HARRIS TECHNOLOGIES"

    def test_preserves_acronyms(self):
        assert normalize_mention("BAE Systems") == "BAE SYSTEMS"

    def test_empty_string(self):
        assert normalize_mention("") == ""


class TestTriage:
    def test_high_confidence_auto_links(self):
        result = triage(similarity=0.95, mention="LOCKHEED MARTIN")
        assert result == ResolutionStatus.AUTO_LINK

    def test_exactly_at_high_threshold_auto_links(self):
        result = triage(similarity=0.92, mention="RAYTHEON")
        assert result == ResolutionStatus.AUTO_LINK

    def test_medium_confidence_llm_call(self):
        result = triage(similarity=0.80, mention="RTX CORP")
        assert result == ResolutionStatus.LLM_DISAMBIGUATE

    def test_exactly_at_medium_threshold_llm_call(self):
        result = triage(similarity=0.70, mention="LMT")
        assert result == ResolutionStatus.LLM_DISAMBIGUATE

    def test_low_confidence_expanded_context(self):
        result = triage(similarity=0.60, mention="SOME CONTRACTOR")
        assert result == ResolutionStatus.LLM_EXPAND_CONTEXT

    def test_exactly_at_low_threshold_expanded_context(self):
        result = triage(similarity=0.55, mention="UNKNOWN ENTITY")
        assert result == ResolutionStatus.LLM_EXPAND_CONTEXT

    def test_very_low_confidence_auto_dismiss(self):
        result = triage(similarity=0.40, mention="AMBIGUOUS NAME")
        assert result == ResolutionStatus.AUTO_DISMISS

    def test_zero_similarity_auto_dismiss(self):
        result = triage(similarity=0.0, mention="")
        assert result == ResolutionStatus.AUTO_DISMISS

    def test_boundary_just_below_high(self):
        result = triage(similarity=0.919, mention="TEST")
        assert result == ResolutionStatus.LLM_DISAMBIGUATE

    def test_boundary_just_below_medium(self):
        result = triage(similarity=0.699, mention="TEST")
        assert result == ResolutionStatus.LLM_EXPAND_CONTEXT

    def test_boundary_just_below_low(self):
        result = triage(similarity=0.549, mention="TEST")
        assert result == ResolutionStatus.AUTO_DISMISS


class TestScoreCandidate:
    def test_exact_match_scores_one(self):
        score = score_candidate(
            mention_normalized="LOCKHEED MARTIN",
            candidate_normalized="LOCKHEED MARTIN",
        )
        assert score == 1.0

    def test_prefix_match_scores_higher_than_unrelated(self):
        # Pure-Python bigram Jaccard; production uses pgvector cosine (higher scores).
        # The key property: prefix match >> completely unrelated pair.
        prefix_score = score_candidate(
            mention_normalized="LOCKHEED MARTIN",
            candidate_normalized="LOCKHEED MARTIN CORPORATION",
        )
        unrelated_score = score_candidate(
            mention_normalized="BOEING",
            candidate_normalized="RAYTHEON",
        )
        assert prefix_score > unrelated_score

    def test_completely_different_scores_low(self):
        score = score_candidate(
            mention_normalized="BOEING",
            candidate_normalized="RAYTHEON",
        )
        assert score < 0.5

    def test_score_is_between_zero_and_one(self):
        score = score_candidate(
            mention_normalized="GENERAL DYNAMICS",
            candidate_normalized="GENERAL MOTORS",
        )
        assert 0.0 <= score <= 1.0


class TestResolutionResult:
    def test_auto_link_result(self):
        result = ResolutionResult(
            status=ResolutionStatus.AUTO_LINK,
            entity_id="some-uuid",
            confidence=0.95,
            resolved_by="auto_high_confidence",
        )
        assert result.entity_id == "some-uuid"
        assert result.is_resolved is True

    def test_auto_dismiss_result_not_resolved(self):
        result = ResolutionResult(
            status=ResolutionStatus.AUTO_DISMISS,
            entity_id=None,
            confidence=0.30,
            resolved_by=None,
        )
        assert result.is_resolved is False

    def test_llm_resolved_result(self):
        result = ResolutionResult(
            status=ResolutionStatus.AUTO_LINK,
            entity_id="another-uuid",
            confidence=0.88,
            resolved_by="llm_auto",
        )
        assert result.is_resolved is True
