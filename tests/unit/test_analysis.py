"""
Tests for engine/brief/analysis.py (D073): the regenerate-then-omit grounding gate.

eval_analysis verdicts and the regeneration LLM call are mocked, so the gate's
control flow (pass-through / regenerate / omit) is tested in isolation.
"""
from unittest.mock import AsyncMock, patch

import pytest
from engine.brief.analysis import ground_brief_analysis, ground_field
from engine.brief.generator import GeneratedBrief
from engine.eval.citation_eval import AnalysisEvalResult


class FakeEvaluator:
    """eval_analysis pops successive (grounded, new_facts) verdicts."""

    def __init__(self, verdicts):
        self.verdicts = list(verdicts)
        self.calls: list[str] = []

    async def eval_analysis(self, analysis, facts):
        self.calls.append(analysis)
        grounded, new_facts = self.verdicts.pop(0)
        return AnalysisEvalResult(grounded=grounded, new_facts=new_facts)


def _patch_regen(return_value="REWRITTEN grounded analysis."):
    return patch(
        "engine.brief.analysis.llm_client.complete",
        new=AsyncMock(return_value=return_value),
    )


class TestGroundField:
    @pytest.mark.asyncio
    async def test_grounded_passes_through_no_regen(self):
        ev = FakeEvaluator([(True, [])])
        with _patch_regen() as regen:
            res = await ground_field(
                "read", "A grounded read.", "facts", ev, model="m", max_regen=1,
            )
        assert res.status == "grounded"
        assert res.text == "A grounded read."
        regen.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_field_is_empty_without_eval(self):
        ev = FakeEvaluator([])  # eval must not be called
        res = await ground_field("watch", "   ", "facts", ev, model="m", max_regen=1)
        assert res.status == "empty"
        assert res.text == ""
        assert ev.calls == []

    @pytest.mark.asyncio
    async def test_flagged_then_regenerated_grounded(self):
        ev = FakeEvaluator([(False, ["invented CARLA-VR"]), (True, [])])
        with _patch_regen("Clean rewrite.") as regen:
            res = await ground_field(
                "read", "Has CARLA-VR.", "facts", ev, model="m", max_regen=1,
            )
        assert res.status == "regenerated"
        assert res.text == "Clean rewrite."
        assert res.fabrications == ["invented CARLA-VR"]
        regen.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_flagged_still_bad_after_regen_is_omitted(self):
        ev = FakeEvaluator([(False, ["fab"]), (False, ["fab again"])])
        with _patch_regen("Still bad rewrite."):
            res = await ground_field(
                "read", "Bad read.", "facts", ev, model="m", max_regen=1,
            )
        assert res.status == "omitted"
        assert res.text == ""
        assert res.fabrications == ["fab"]   # the original flag is reported

    @pytest.mark.asyncio
    async def test_max_regen_zero_omits_immediately(self):
        ev = FakeEvaluator([(False, ["fab"])])
        with _patch_regen() as regen:
            res = await ground_field(
                "read", "Bad read.", "facts", ev, model="m", max_regen=0,
            )
        assert res.status == "omitted"
        assert res.text == ""
        regen.assert_not_called()

    @pytest.mark.asyncio
    async def test_regen_returning_empty_omits(self):
        ev = FakeEvaluator([(False, ["fab"])])  # only the first eval runs
        with _patch_regen(""):   # nothing grounded left to say
            res = await ground_field(
                "read", "Bad read.", "facts", ev, model="m", max_regen=1,
            )
        assert res.status == "omitted"
        assert res.text == ""


class TestGroundBriefAnalysis:
    def _brief(self):
        return GeneratedBrief(
            headline="H", bluf="B",
            items=[
                {"headline": "i0", "body": "b0", "read": "R0", "watch": ""},
                {"headline": "i1", "body": "b1", "read": "R1", "watch": "W1"},
            ],
            passages=[], synthesis_model="m",
            convergence_read="Conv read.",
        )

    @pytest.mark.asyncio
    async def test_all_grounded_mutates_in_place(self):
        brief = self._brief()
        # 4 non-empty fields evaluated: convergence, i0.read, i1.read, i1.watch
        ev = FakeEvaluator([(True, [])] * 4)
        report = await ground_brief_analysis(
            brief, brief.items, "facts", ev, max_regen=1,
        )
        assert brief.convergence_read == "Conv read."
        assert brief.items[0]["read"] == "R0"
        assert brief.items[0]["watch"] == ""      # stays empty
        assert brief.items[1]["watch"] == "W1"
        # one report row per field processed: convergence + 2 items × (read, watch)
        assert len(report) == 5
        statuses = {r.label: r.status for r in report}
        assert statuses["item0.watch"] == "empty"

    @pytest.mark.asyncio
    async def test_omitted_field_blanked_in_place(self):
        brief = self._brief()
        # convergence ok; i0.read flagged + regen still bad → omit; i1.read/watch ok
        ev = FakeEvaluator([
            (True, []),                 # convergence
            (False, ["fab"]),           # i0.read original
            (False, ["fab"]),           # i0.read after regen
            (True, []),                 # i1.read
            (True, []),                 # i1.watch
        ])
        with _patch_regen("still bad"):
            await ground_brief_analysis(brief, brief.items, "facts", ev, max_regen=1)
        assert brief.items[0]["read"] == ""        # omitted
        assert brief.items[1]["read"] == "R1"
