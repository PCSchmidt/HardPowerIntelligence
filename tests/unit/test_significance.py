"""Strategic-significance gate (D085). Pure threshold logic + mocked triage call."""
from unittest.mock import AsyncMock, patch

import pytest
from engine.brief.significance import apply_significance, filter_significant


def _fact(text: str, mat: float = 0.5):
    return ({"text_chunk": text}, mat)


class TestApplyThreshold:
    def test_keeps_above_drops_below(self):
        facts = [_fact("big award"), _fact("phone contract"), _fact("breakthrough")]
        scores = {0: (0.9, "material award"), 1: (0.1, "routine telecom"), 2: (0.8, "tech")}
        kept, dropped = apply_significance(facts, scores, threshold=0.45)
        assert len(kept) == 2
        assert {d[0] for d in dropped} == {"phone contract"}
        assert dropped[0][2] == "routine telecom"   # reason preserved

    def test_unscored_is_failed_open_kept(self):
        # the model returned no score for id=1 → it must be KEPT, not dropped
        facts = [_fact("a"), _fact("b")]
        kept, dropped = apply_significance(facts, {0: (0.9, "x")}, threshold=0.45)
        assert len(kept) == 2 and dropped == []

    def test_never_returns_empty_keeps_best(self):
        # everything below threshold → keep the single highest-scoring fact
        facts = [_fact("a"), _fact("b"), _fact("c")]
        scores = {0: (0.2, "low"), 1: (0.35, "best of bad"), 2: (0.1, "low")}
        kept, dropped = apply_significance(facts, scores, threshold=0.45)
        assert len(kept) == 1
        assert kept[0][0]["text_chunk"] == "b"        # the 0.35 one survives
        assert len(dropped) == 2                       # the other two reported dropped

    def test_empty_input(self):
        assert apply_significance([], {}, 0.45) == ([], [])


class TestFilterSignificant:
    @pytest.mark.asyncio
    async def test_disabled_passes_through(self, monkeypatch):
        monkeypatch.setattr("engine.brief.significance.settings.significance_enabled", False)
        facts = [_fact("x")]
        kept, dropped = await filter_significant(facts, "energy")
        assert kept == facts and dropped == []

    @pytest.mark.asyncio
    async def test_triage_failure_fails_open(self, monkeypatch):
        monkeypatch.setattr("engine.brief.significance.settings.significance_enabled", True)
        facts = [_fact("x"), _fact("y")]
        with patch(
            "engine.brief.significance.llm_client.complete",
            new=AsyncMock(side_effect=RuntimeError("triage down")),
        ):
            kept, dropped = await filter_significant(facts, "energy")
        assert kept == facts and dropped == []          # outage → keep everything

    @pytest.mark.asyncio
    async def test_end_to_end_drop(self, monkeypatch):
        monkeypatch.setattr("engine.brief.significance.settings.significance_enabled", True)
        monkeypatch.setattr("engine.brief.significance.settings.significance_threshold", 0.45)
        facts = [_fact("$700M liquid cooling deal"), _fact("routine cellular service contract")]
        payload = (
            '{"scores":[{"id":0,"score":0.9,"reason":"material deal"},'
            '{"id":1,"score":0.1,"reason":"commodity telecom"}]}'
        )
        with patch(
            "engine.brief.significance.llm_client.complete",
            new=AsyncMock(return_value=payload),
        ):
            kept, dropped = await filter_significant(facts, "defense")
        assert len(kept) == 1 and kept[0][0]["text_chunk"] == "$700M liquid cooling deal"
        assert len(dropped) == 1
