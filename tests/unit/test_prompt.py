"""Synthesis prompt is desk-aware (D060 multi-desk).

Spec: the analyst persona must match the desk — not a hardcoded "Defense" one —
and the citation discipline must be present for every desk.
"""
from engine.brief.prompt import build_synthesis_prompt


def _system(desk: str) -> str:
    msgs = build_synthesis_prompt(desk=desk, passages=[], verified_facts=[], max_items=3)
    return next(m["content"] for m in msgs if m["role"] == "system")


def test_energy_persona_not_defense():
    sys = _system("energy")
    assert "ENERGY desk" in sys
    assert "energy-technology" in sys
    assert "Defense intelligence analyst" not in sys  # the old hardcoded bug


def test_ai_persona():
    sys = _system("ai")
    assert "AI desk" in sys
    assert "artificial-intelligence" in sys


def test_defense_persona_preserved():
    sys = _system("defense")
    assert "DEFENSE desk" in sys
    assert "defense-technology" in sys


def test_citation_rule_present_for_all_desks():
    for desk in ("defense", "ai", "energy"):
        msgs = build_synthesis_prompt(desk=desk, passages=[], verified_facts=[], max_items=3)
        user = next(m["content"] for m in msgs if m["role"] == "user")
        assert "[CITE:N]" in user
