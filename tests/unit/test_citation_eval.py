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
    strip_uncited_sentences,
)


class TestStripUncitedSentences:
    def test_keeps_cited_drops_uncited(self):
        body = (
            "SAIC won a $586M CBP contract [CITE:5]. "
            "This modernizes border security infrastructure."
        )
        cleaned = strip_uncited_sentences(body)
        assert cleaned == "SAIC won a $586M CBP contract [CITE:5]."

    def test_all_cited_unchanged(self):
        body = "Triad won $35B [CITE:1]. Leidos won $3B [CITE:2]."
        assert strip_uncited_sentences(body) == body

    def test_all_uncited_returns_empty(self):
        assert strip_uncited_sentences("No citations here. Still none.") == ""

    def test_empty_body(self):
        assert strip_uncited_sentences("") == ""

    def test_cleaned_body_has_no_uncited_claims(self):
        # After cleaning, every extracted claim must be cited (the eval invariant).
        body = "A [CITE:1]. B. C [CITE:2]. D."
        cleaned = strip_uncited_sentences(body)
        assert all(c.is_cited for c in extract_claims(cleaned))


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


class TestProvableClaimCount:
    """D070: publish gate counts provable claims, not items, so it's stable whether
    synthesis consolidates facts into few dense items or expands to many thin ones."""

    def _ev(self):
        return CitationEvaluator(eval_model="m")

    def test_sums_passing_over_surviving(self):
        # Two dense items (3 + 6 provable) == 9, same as if spread over nine items.
        results = [
            EvalResult(item_id="i1", excluded=False, claims_total=3, claims_passing=3, faithfulness_score=1.0),
            EvalResult(item_id="i2", excluded=False, claims_total=6, claims_passing=6, faithfulness_score=1.0),
        ]
        assert self._ev().provable_claim_count(results) == 9

    def test_excluded_items_dont_count(self):
        results = [
            EvalResult(item_id="i1", excluded=False, claims_total=2, claims_passing=2, faithfulness_score=1.0),
            EvalResult(item_id="i2", excluded=True, claims_total=3, claims_passing=0, faithfulness_score=0.0),
        ]
        assert self._ev().provable_claim_count(results) == 2

    def test_trimmed_item_counts_only_supported_claims(self):
        # A partially over-claimed item (4 written, 1 supported) contributes 1.
        results = [
            EvalResult(item_id="i1", excluded=False, claims_total=4, claims_passing=1, faithfulness_score=0.25),
        ]
        assert self._ev().provable_claim_count(results) == 1

    def test_stable_across_consolidation_vs_expansion(self):
        # Same 6 facts, packed as 1 dense item or 6 thin items → identical count.
        dense = [EvalResult(item_id="d", excluded=False, claims_total=6, claims_passing=6, faithfulness_score=1.0)]
        expanded = [
            EvalResult(item_id=f"e{i}", excluded=False, claims_total=1, claims_passing=1, faithfulness_score=1.0)
            for i in range(6)
        ]
        ev = self._ev()
        assert ev.provable_claim_count(dense) == ev.provable_claim_count(expanded) == 6

    def test_empty_results_zero(self):
        assert self._ev().provable_claim_count([]) == 0


class TestEvalAnalysis:
    """D071: the analysis layer ('read'/'watch'/'convergence') is interpretation —
    no citations required, but it must introduce no concrete fact absent from the
    cited fact set. eval_analysis is the grounding guardrail that makes layered
    briefs possible without breaking the trust model."""

    def _ev(self):
        return CitationEvaluator(eval_model="m")

    @pytest.mark.asyncio
    async def test_grounded_interpretation_passes(self):
        with patch("engine.eval.citation_eval.llm_client") as mock_client:
            mock_client.complete = AsyncMock(return_value=json.dumps({"new_facts": []}))
            r = await self._ev().eval_analysis(
                "This continues a pattern of seeding the upstream supply chain.",
                "DOE awarded $5.9M to Sustainable Energy Solutions.",
            )
        assert r.grounded
        assert r.new_facts == []

    @pytest.mark.asyncio
    async def test_fabricated_fact_flagged(self):
        with patch("engine.eval.citation_eval.llm_client") as mock_client:
            mock_client.complete = AsyncMock(return_value=json.dumps(
                {"new_facts": ["asserts a $2B follow-on award not in the facts"]}
            ))
            r = await self._ev().eval_analysis(
                "A $2B follow-on award is imminent.",
                "DOE awarded $5.9M to Sustainable Energy Solutions.",
            )
        assert not r.grounded
        assert len(r.new_facts) == 1

    @pytest.mark.asyncio
    async def test_empty_analysis_is_grounded_without_llm_call(self):
        with patch("engine.eval.citation_eval.llm_client") as mock_client:
            mock_client.complete = AsyncMock(side_effect=AssertionError("should not call LLM"))
            r = await self._ev().eval_analysis("   ", "some facts")
        assert r.grounded
        assert r.new_facts == []

    @pytest.mark.asyncio
    async def test_blank_strings_in_new_facts_ignored(self):
        with patch("engine.eval.citation_eval.llm_client") as mock_client:
            mock_client.complete = AsyncMock(return_value=json.dumps({"new_facts": ["", "  "]}))
            r = await self._ev().eval_analysis("Some read.", "facts")
        assert r.grounded          # only blank entries → treated as none
        assert r.new_facts == []


class TestEvalAnalysesBatch:
    """D119: ground many fields in ONE call (facts sent once). Per-label verdicts map back;
    a label the model omits fails open (grounded), because the analysis layer is decorative."""

    def _ev(self):
        return CitationEvaluator(eval_model="m")

    @pytest.mark.asyncio
    async def test_per_label_verdicts_mapped_in_one_call(self):
        reply = json.dumps({"results": [
            {"label": "convergence_read", "new_facts": []},
            {"label": "item0.read", "new_facts": ["invents a $2B award"]},
        ]})
        with patch("engine.eval.citation_eval.llm_client") as mock_client:
            mock_client.complete = AsyncMock(return_value=reply)
            out = await self._ev().eval_analyses_batch(
                [("convergence_read", "conv"), ("item0.read", "bad read")], "facts",
            )
            assert mock_client.complete.await_count == 1     # ONE call for all fields
        assert out["convergence_read"].grounded
        assert not out["item0.read"].grounded
        assert out["item0.read"].new_facts == ["invents a $2B award"]

    @pytest.mark.asyncio
    async def test_omitted_label_fails_open_grounded(self):
        # Model returns nothing for item1.watch → default grounded, not silently dropped.
        with patch("engine.eval.citation_eval.llm_client") as mock_client:
            mock_client.complete = AsyncMock(return_value=json.dumps({"results": []}))
            out = await self._ev().eval_analyses_batch([("item1.watch", "a watch")], "facts")
        assert out["item1.watch"].grounded

    @pytest.mark.asyncio
    async def test_no_fields_makes_no_call(self):
        with patch("engine.eval.citation_eval.llm_client") as mock_client:
            mock_client.complete = AsyncMock(side_effect=AssertionError("should not call LLM"))
            out = await self._ev().eval_analyses_batch([("a", "   "), ("b", "")], "facts")
        assert out == {}


class TestCleanedBody:
    """D069: eval_item returns a cleaned_body of only the individually-supported,
    cited sentences, so a partially over-claimed item is trimmed rather than
    dragging the brief below threshold (the non-determinism failure mode)."""

    def _passages(self):
        from datetime import datetime, timezone

        from engine.brief.rag import PassageContext
        return [PassageContext(
            index=1, raw_record_id="r1", source_id="usaspending",
            url="https://x", fetched_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
            native_id="n1", excerpt="Award amount $1.1B for LRASM",
        )]

    @pytest.mark.asyncio
    async def test_trims_unsupported_sentence_keeps_supported(self):
        with patch("engine.eval.citation_eval.llm_client") as mock_client:
            mock_client.complete = AsyncMock(return_value=json.dumps(
                {"claim_evaluations": [
                    {"id": "c0", "supported": True},
                    {"id": "c1", "supported": False},
                ]}
            ))
            evaluator = CitationEvaluator(eval_model="m")
            result = await evaluator.eval_item(
                item_id="i",
                body="LM won $1.1B [CITE:1]. It triples national capacity [CITE:1].",
                passages=self._passages(),
            )
        # Only the supported first sentence survives; the over-claim is dropped.
        assert result.cleaned_body == "LM won $1.1B [CITE:1]."
        assert not result.excluded
        assert result.faithfulness_score == pytest.approx(0.5)  # pre-clean score unchanged

    @pytest.mark.asyncio
    async def test_all_unsupported_excluded_with_empty_cleaned_body(self):
        with patch("engine.eval.citation_eval.llm_client") as mock_client:
            mock_client.complete = AsyncMock(return_value=json.dumps(
                {"claim_evaluations": [{"id": "c0", "supported": False}]}
            ))
            evaluator = CitationEvaluator(eval_model="m")
            result = await evaluator.eval_item(
                item_id="i", body="Unsupported claim [CITE:1].", passages=self._passages(),
            )
        assert result.excluded
        assert result.cleaned_body == ""

    @pytest.mark.asyncio
    async def test_cleaned_body_is_fully_cited(self):
        with patch("engine.eval.citation_eval.llm_client") as mock_client:
            mock_client.complete = AsyncMock(return_value=json.dumps(
                {"claim_evaluations": [{"id": "c1", "supported": True}]}
            ))
            evaluator = CitationEvaluator(eval_model="m")
            result = await evaluator.eval_item(
                item_id="i",
                body="Uncited background sentence. Supported fact [CITE:1].",
                passages=self._passages(),
            )
        # Uncited sentence already gone; only the supported, cited one remains.
        assert result.cleaned_body == "Supported fact [CITE:1]."
        assert all(c.is_cited for c in extract_claims(result.cleaned_body))
