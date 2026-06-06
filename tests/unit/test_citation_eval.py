"""
Tests for engine/eval/citation_eval.py (D029, D038).
All LLM calls mocked — no network.
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

from engine.eval.citation_eval import (
    CitationEvaluator,
    EvalResult,
    extract_claims,
    extract_citation_indices,
)


class TestExtractClaims:
    def test_single_sentence(self):
        body = "Lockheed Martin was awarded $1.1B for LRASM production [CITE:1]."
        claims = extract_claims(body)
        assert len(claims) == 1
        assert claims[0].text == "Lockheed Martin was awarded $1.1B for LRASM production [CITE:1]."

    def test_multiple_sentences(self):
        body = (
            "Lockheed Martin was awarded $1.1B for LRASM [CITE:1]. "
            "The contract runs through FY2028 [CITE:2]. "
            "This represents a 15% increase over prior year [CITE:1]."
        )
        claims = extract_claims(body)
        assert len(claims) == 3

    def test_uncited_sentence_marked_uncited(self):
        body = "Some uncited claim. Cited claim [CITE:1]."
        claims = extract_claims(body)
        assert not claims[0].is_cited
        assert claims[1].is_cited

    def test_citation_indices_extracted(self):
        body = "Award of $500M [CITE:2] for program [CITE:5]."
        claims = extract_claims(body)
        assert 2 in claims[0].citation_indices
        assert 5 in claims[0].citation_indices

    def test_empty_body_returns_empty(self):
        assert extract_claims("") == []


class TestExtractCitationIndices:
    def test_single_cite(self):
        assert extract_citation_indices("text [CITE:3]") == [3]

    def test_multiple_cites(self):
        assert extract_citation_indices("a [CITE:1] b [CITE:4]") == [1, 4]

    def test_no_cites(self):
        assert extract_citation_indices("no citations here") == []

    def test_deduplicates(self):
        assert extract_citation_indices("[CITE:2] and again [CITE:2]") == [2]


class TestCitationEvaluator:
    def _make_passages(self):
        from engine.brief.rag import PassageContext
        from datetime import datetime, timezone
        return [
            PassageContext(
                index=1,
                raw_record_id="rec-1",
                source_id="usaspending",
                url="https://usaspending.gov/award/DAAH23-26-C-0042/",
                fetched_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
                native_id="DAAH23-26-C-0042",
                excerpt="Award amount: $1,100,000,000; LRASM production FY26-29",
            ),
            PassageContext(
                index=2,
                raw_record_id="rec-2",
                source_id="usaspending",
                url="https://usaspending.gov/award/N00019-26-C-0101/",
                fetched_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
                native_id="N00019-26-C-0101",
                excerpt="Award amount: $487,500,000; AMRAAM production FY26-28",
            ),
        ]

    def _mock_qwen_response(self, evaluations):
        mock = AsyncMock()
        mock.return_value = json.dumps({"claim_evaluations": evaluations})
        return mock

    @pytest.mark.asyncio
    async def test_all_claims_pass_score_one(self):
        evaluations = [
            {"id": "c0", "supported": True},
            {"id": "c1", "supported": True},
        ]
        passages = self._make_passages()

        with patch("engine.eval.citation_eval.llm_client") as mock_client:
            mock_client.complete = self._mock_qwen_response(evaluations)
            evaluator = CitationEvaluator(eval_model="openrouter/qwen/qwen3.7-max")
            result = await evaluator.eval_item(
                item_id="item-1",
                body="LM awarded $1.1B [CITE:1]. Contract FY26-29 [CITE:1].",
                passages=passages,
            )

        assert result.faithfulness_score == 1.0
        assert not result.excluded

    @pytest.mark.asyncio
    async def test_all_claims_fail_item_excluded(self):
        evaluations = [
            {"id": "c0", "supported": False},
            {"id": "c1", "supported": False},
        ]
        passages = self._make_passages()

        with patch("engine.eval.citation_eval.llm_client") as mock_client:
            mock_client.complete = self._mock_qwen_response(evaluations)
            evaluator = CitationEvaluator(eval_model="openrouter/qwen/qwen3.7-max")
            result = await evaluator.eval_item(
                item_id="item-1",
                body="False claim [CITE:1]. Another false claim [CITE:2].",
                passages=passages,
            )

        assert result.excluded

    @pytest.mark.asyncio
    async def test_uncited_sentence_fails(self):
        passages = self._make_passages()
        evaluator = CitationEvaluator(eval_model="openrouter/qwen/qwen3.7-max")

        with patch("engine.eval.citation_eval.llm_client") as mock_client:
            mock_client.complete = self._mock_qwen_response([{"id": "c1", "supported": True}])
            result = await evaluator.eval_item(
                item_id="item-1",
                body="Uncited claim with no reference. Cited claim [CITE:1].",
                passages=passages,
            )

        # 1 uncited (fails) + 1 cited (passes) → 0.5
        assert result.faithfulness_score == pytest.approx(0.5)

    def test_brief_faithfulness_score_excludes_failed_items(self):
        evaluator = CitationEvaluator(eval_model="openrouter/qwen/qwen3.7-max")
        item_results = [
            EvalResult(item_id="i1", excluded=False, claims_total=4, claims_passing=4, faithfulness_score=1.0),
            EvalResult(item_id="i2", excluded=True, claims_total=3, claims_passing=0, faithfulness_score=0.0),
            EvalResult(item_id="i3", excluded=False, claims_total=3, claims_passing=3, faithfulness_score=1.0),
        ]
        score = evaluator.brief_faithfulness_score(item_results)
        # Only i1 and i3 count: 7/7 = 1.0
        assert score == pytest.approx(1.0)

    def test_brief_faithfulness_score_partial(self):
        evaluator = CitationEvaluator(eval_model="openrouter/qwen/qwen3.7-max")
        item_results = [
            EvalResult(item_id="i1", excluded=False, claims_total=4, claims_passing=3, faithfulness_score=0.75),
            EvalResult(item_id="i2", excluded=False, claims_total=4, claims_passing=4, faithfulness_score=1.0),
        ]
        score = evaluator.brief_faithfulness_score(item_results)
        # 7/8 = 0.875
        assert score == pytest.approx(0.875)

    def test_all_items_excluded_returns_zero(self):
        evaluator = CitationEvaluator(eval_model="openrouter/qwen/qwen3.7-max")
        item_results = [
            EvalResult(item_id="i1", excluded=True, claims_total=3, claims_passing=0, faithfulness_score=0.0),
        ]
        assert evaluator.brief_faithfulness_score(item_results) == 0.0
