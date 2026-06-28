"""
Tests for engine/brief/publish.py — the publish gate.

The widen-the-net flip (D099): grounding level is no longer a suppression gate (the
old D070 provable-claim floor). A brief publishes when it has ≥1 honest item; each
surviving item is stamped an epistemic attribution label (D098). The one hard line
stays: an item with NO source-supported content is still excluded (anti-fabrication,
D069). Regenerate-on-failure (D072) now retries only a genuinely empty/failed draw.

generate_brief is mocked (no DB / no LLM); the evaluator is a minimal fake whose
verdict is encoded in each item body, so the loop logic is tested in isolation.
"""
from unittest.mock import AsyncMock, patch

import pytest
from engine.brief.epistemics import Attribution
from engine.brief.generator import GeneratedBrief
from engine.brief.publish import evaluate_brief, generate_publishable_brief
from engine.eval.citation_eval import EvalResult

_VALID_ATTRIBUTIONS = {a.value for a in Attribution}


class FakeEvaluator:
    """Stand-in for CitationEvaluator. ``eval_item`` reads its verdict from the item
    body: ``"excluded"`` → dropped (no support); ``"claims=N"`` → N supported claims."""

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
    async def test_excludes_unsupported_keeps_supported(self):
        # The hard line holds: a zero-support item is still excluded (anti-fabrication).
        brief = _brief("claims=2", "excluded", "claims=1")
        attempt = await evaluate_brief(brief, FakeEvaluator(), min_claims=3)

        assert attempt.provable_claims == 3   # retained as a metric
        assert attempt.eval_passed is True
        assert attempt.excluded_ids == {"item-1"}
        assert [it["_item_id"] for it in attempt.surviving_items] == ["item-0", "item-2"]

    @pytest.mark.asyncio
    async def test_thin_brief_now_publishes(self):
        # THE FLIP: a single supported claim used to fail the ≥3 provable-claim floor.
        # Now one honest item is enough to publish — grounding labels, doesn't suppress.
        brief = _brief("claims=1")
        attempt = await evaluate_brief(brief, FakeEvaluator(), min_claims=3)
        assert attempt.provable_claims == 1
        assert attempt.eval_passed is True

    @pytest.mark.asyncio
    async def test_no_honest_items_does_not_publish(self):
        # Only when nothing honest survives does the brief fail to publish.
        brief = _brief("excluded", "excluded")
        attempt = await evaluate_brief(brief, FakeEvaluator(), min_claims=3)
        assert attempt.eval_passed is False
        assert attempt.surviving_items == []

    @pytest.mark.asyncio
    async def test_surviving_items_carry_a_valid_attribution(self):
        brief = _brief("claims=2", "excluded", "claims=1")
        attempt = await evaluate_brief(brief, FakeEvaluator(), min_claims=3)
        for it in attempt.surviving_items:
            assert it["attribution"] in _VALID_ATTRIBUTIONS
        # the excluded item is never stamped/published
        assert "attribution" not in brief.items[1]


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
    async def test_retries_an_empty_draw_until_one_has_content(self):
        # First draw has no honest items (bad synthesis draw); the loop retries.
        briefs = [_brief("excluded"), _brief("claims=2", "claims=1")]
        with patch(
            "engine.brief.publish.generate_brief",
            new=AsyncMock(side_effect=briefs),
        ) as gen:
            attempt = await generate_publishable_brief(
                desk="defense", pool=None, evaluator=FakeEvaluator(),
                min_claims=3, max_attempts=3,
            )
        assert attempt.eval_passed is True
        assert len(attempt.surviving_items) == 2
        assert gen.call_count == 2

    @pytest.mark.asyncio
    async def test_returns_best_attempt_when_all_empty(self):
        # Every draw is empty → return the best (most surviving), marked failed.
        briefs = [_brief("excluded"), _brief("excluded", "excluded"), _brief("excluded")]
        with patch(
            "engine.brief.publish.generate_brief",
            new=AsyncMock(side_effect=briefs),
        ) as gen:
            attempt = await generate_publishable_brief(
                desk="defense", pool=None, evaluator=FakeEvaluator(),
                min_claims=3, max_attempts=3,
            )
        assert attempt.eval_passed is False
        assert attempt.surviving_items == []
        assert gen.call_count == 3

    @pytest.mark.asyncio
    async def test_max_attempts_one_disables_retry(self):
        with patch(
            "engine.brief.publish.generate_brief",
            new=AsyncMock(side_effect=[_brief("excluded")]),
        ) as gen:
            attempt = await generate_publishable_brief(
                desk="defense", pool=None, evaluator=FakeEvaluator(),
                min_claims=3, max_attempts=1,
            )
        assert attempt.eval_passed is False
        assert gen.call_count == 1

    @pytest.mark.asyncio
    async def test_generation_exception_is_retried(self):
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
    async def test_exception_then_empty_draw_returns_best_not_crash(self):
        # One attempt raises, the other is empty — return the (failed) brief, don't crash.
        with patch(
            "engine.brief.publish.generate_brief",
            new=AsyncMock(side_effect=[RuntimeError("stall"), _brief("excluded")]),
        ) as gen:
            attempt = await generate_publishable_brief(
                desk="defense", pool=None, evaluator=FakeEvaluator(),
                min_claims=3, max_attempts=2,
            )
        assert attempt.eval_passed is False
        assert gen.call_count == 2

    @pytest.mark.asyncio
    async def test_uses_settings_defaults_when_unspecified(self):
        with patch(
            "engine.brief.publish.generate_brief",
            new=AsyncMock(side_effect=[_brief("claims=3")]),
        ) as gen:
            attempt = await generate_publishable_brief(
                desk="defense", pool=None, evaluator=FakeEvaluator(),
            )
        assert attempt.eval_passed is True
        assert gen.call_count == 1
