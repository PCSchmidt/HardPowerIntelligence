"""LLM token accumulator (Phase A / A4).

The client tallies completion-call tokens across a process (= one desk-run in CI) so run_brief
can stamp cost onto the brief and the health digest can aggregate it.
"""
from types import SimpleNamespace

from engine.llm.client import LLMClient


def _response(prompt, completion):
    return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion))


def test_accumulates_across_calls():
    c = LLMClient()
    c._record_usage("m", _response(100, 40))
    c._record_usage("m", _response(200, 60))
    snap = c.usage_snapshot()
    assert snap["calls"] == 2
    assert snap["prompt_tokens"] == 300
    assert snap["completion_tokens"] == 100
    assert snap["total_tokens"] == 400


def test_est_cost_uses_blended_rate():
    c = LLMClient()
    c._record_usage("m", _response(600_000, 400_000))  # 1.0M tokens
    snap = c.usage_snapshot()
    # 1.0M tokens * $0.60/1M = $0.60 (default blended rate)
    assert snap["total_tokens"] == 1_000_000
    assert snap["est_cost_usd"] == 0.6


def test_reset_zeros_counters():
    c = LLMClient()
    c._record_usage("m", _response(10, 5))
    c.reset_usage()
    assert c.usage_snapshot() == {
        "calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
        "total_tokens": 0, "est_cost_usd": 0.0,
    }


def test_missing_usage_is_ignored():
    c = LLMClient()
    c._record_usage("m", SimpleNamespace(usage=None))
    assert c.usage_snapshot()["calls"] == 0
