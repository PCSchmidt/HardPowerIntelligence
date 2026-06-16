"""
Tests for engine/brief/publish.py (D072): the publish gate with
regenerate-on-failure. The synthesis model is non-deterministic, so a failed gate
is often a bad draw a re-run clears — these verify the loop returns the first
passing attempt, retries on failure, and falls back to the best attempt seen.

generate_brief is mocked (no DB / no LLM); the evaluator is a minimal fake whose
verdict is encoded in each item body, so the loop logic is tested in isolation.
"""
from unittest.mock import AsyncMock, patch

import pytest
from engine.brief.generator import GeneratedBrief
from engine.brief.publish import evaluate_brief, generate_publishable_brief
from engine.eval.citation_eval import EvalResult


class FakeEvaluator:
    """Stand-in for CitationEvaluator. ``eval_item`` reads its verdict from the item
    body: ``"excluded"`` → dropped; ``"claims=N"`` → N supported claims."""

    def __init__(self):
        self.eval_calls = 0

    async def eval_item(self, item_id, body, passages):
        self.eval_calls += 1
        if body == "excluded":
            return EvalResult(
                item_id=item_id, excluded=True,
                claims_total=2, claims_passing=0, faithfulness_score=0.0,
            )
        n = int(body.split("=")[1])
        return EvalResult(
            item_id=item_id, excluded=False,
            claims_total=n, claims_passing=n, faithfulness_score=1.0,
            cleaned_body=body,
        )

    def provable_claim_count(self, results):
        return sum(r.claims_passing for r in results if not r.excluded)


def _brief(*item_bodies) -> GeneratedBrief:
    return GeneratedBrief(
        headline="h", bluf="b",
        items=[{"headline": f"item {i}", "body": b} for i, b in enumerate(item_bodies)],
        passages=[], synthesis_model="m",
    )


class TestEvaluateBrief:
    @pytest.mark.asyncio
    async def test_counts_claims_and_marks_excluded(self):
        brief = _brief("claims=2", "excluded", "claims=1")
        attempt = await evaluate_brief(brief, FakeEvaluator(), min_claims=3)

        assert attempt.provable_claims == 3
        assert attempt.eval_passed is True
        assert attempt.excluded_ids == {"item-1"}
        # surviving items carry their _item_id and the cleaned body
        assert [it["_item_id"] for it in attempt.surviving_items] == ["item-0", "item-2"]
        assert brief.items[1]["_item_id"] == "item-1"

    @pytest.mark.asyncio
    async def test_below_floor_does_not_pass(self):
        brief = _brief("claims=1", "excluded")
        attempt = await evaluate_brief(brief, FakeEvaluator(), min_claims=3)
        assert attempt.provable_claims == 1
        assert attempt.eval_passed is False


class TestGeneratePublishableBrief:
    @pytest.mark.asyncio
    async def test_returns_first_passing_attempt_no_retry(self):
        with patch(
            "engine.brief.publish.generate_brief",
            new=AsyncMock(side_effect=[_brief("claims=3")]),
        ) as gen:
            attempt = await generate_publishable_brief(
                desk="defense", pool=None, evaluator=FakeEvaluator(),
                min_claims=3, max_attempts=3,
            )
        assert attempt.eval_passed is True
        assert gen.call_count == 1   # stopped on first pass

    @pytest.mark.asyncio
    async def test_retries_until_pass(self):
        briefs = [_brief("claims=1"), _brief("claims=2"), _brief("claims=3", "claims=1")]
        with patch(
            "engine.brief.publish.generate_brief",
            new=AsyncMock(side_effect=briefs),
        ) as gen:
            attempt = await generate_publishable_brief(
                desk="defense", pool=None, evaluator=FakeEvaluator(),
                min_claims=3, max_attempts=3,
            )
        assert attempt.eval_passed is True
        assert attempt.provable_claims == 4
        assert gen.call_count == 3

    @pytest.mark.asyncio
    async def test_returns_best_attempt_when_all_fail(self):
        # provable claims 1, 2, 0 across attempts — best (2) is returned, marked failed.
        briefs = [_brief("claims=1"), _brief("claims=2"), _brief("excluded")]
        with patch(
            "engine.brief.publish.generate_brief",
            new=AsyncMock(side_effect=briefs),
        ) as gen:
            attempt = await generate_publishable_brief(
                desk="defense", pool=None, evaluator=FakeEvaluator(),
                min_claims=3, max_attempts=3,
            )
        assert attempt.eval_passed is False
        assert attempt.provable_claims == 2   # the strongest draw
        assert gen.call_count == 3

    @pytest.mark.asyncio
    async def test_max_attempts_one_disables_retry(self):
        with patch(
            "engine.brief.publish.generate_brief",
            new=AsyncMock(side_effect=[_brief("claims=1")]),
        ) as gen:
            attempt = await generate_publishable_brief(
                desk="defense", pool=None, evaluator=FakeEvaluator(),
                min_claims=3, max_attempts=1,
            )
        assert attempt.eval_passed is False
        assert gen.call_count == 1

    @pytest.mark.asyncio
    async def test_generation_exception_is_retried(self):
        # First attempt raises (e.g. synthesis returned whitespace → JSON error);
        # the loop retries and the second attempt publishes.
        with patch(
            "engine.brief.publish.generate_brief",
            new=AsyncMock(side_effect=[RuntimeError("whitespace stall"), _brief("claims=3")]),
        ) as gen:
            attempt = await generate_publishable_brief(
                desk="defense", pool=None, evaluator=FakeEvaluator(),
                min_claims=3, max_attempts=3,
            )
        assert attempt.eval_passed is True
        assert gen.call_count == 2

    @pytest.mark.asyncio
    async def test_all_attempts_raise_reraises_runtimeerror(self):
        original = ValueError("provider exploded")
        with patch(
            "engine.brief.publish.generate_brief",
            new=AsyncMock(side_effect=[original, original]),
        ) as gen:
            with pytest.raises(RuntimeError, match="after 2 attempt"):
                await generate_publishable_brief(
                    desk="defense", pool=None, evaluator=FakeEvaluator(),
                    min_claims=3, max_attempts=2,
                )
        assert gen.call_count == 2

    @pytest.mark.asyncio
    async def test_exception_then_failed_gate_returns_best_not_crash(self):
        # One attempt raises, the other produces a sub-floor brief — return the brief
        # (marked failed) rather than crashing on the earlier exception.
        with patch(
            "engine.brief.publish.generate_brief",
            new=AsyncMock(side_effect=[RuntimeError("stall"), _brief("claims=1")]),
        ) as gen:
            attempt = await generate_publishable_brief(
                desk="defense", pool=None, evaluator=FakeEvaluator(),
                min_claims=3, max_attempts=2,
            )
        assert attempt.eval_passed is False
        assert attempt.provable_claims == 1
        assert gen.call_count == 2

    @pytest.mark.asyncio
    async def test_uses_settings_defaults_when_unspecified(self):
        # min_claims / max_attempts omitted → pulled from settings (3 / 3).
        with patch(
            "engine.brief.publish.generate_brief",
            new=AsyncMock(side_effect=[_brief("claims=3")]),
        ) as gen:
            attempt = await generate_publishable_brief(
                desk="defense", pool=None, evaluator=FakeEvaluator(),
            )
        assert attempt.eval_passed is True
        assert gen.call_count == 1
