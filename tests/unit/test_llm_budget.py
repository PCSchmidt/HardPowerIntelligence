"""Per-run cost circuit breaker (D159).

A single desk-run is refused further LLM calls once its estimated spend crosses `llm_run_budget_usd`,
so a loop/glitch is bounded per process (degrades via LLMBudgetExceeded) instead of racking up an
unbounded bill. Checked BEFORE the call, so nothing is spent past the ceiling."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from engine.llm.client import LLMBudgetExceeded, LLMClient
from engine.settings import settings


def _ok(content='{"ok": true}'):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )


@pytest.mark.asyncio
class TestRunBudgetBreaker:
    async def test_refuses_call_once_budget_spent_before_any_request(self):
        client = LLMClient()
        with (
            patch.object(settings, "llm_run_budget_usd", 1.0),
            patch.object(settings, "llm_cost_per_1m_tokens_usd", 1.0),
        ):
            client._completion_tokens = 2_000_000  # est_cost = 2M/1M * $1.00 = $2.00 ≥ $1.00 budget
            with patch("engine.llm.client.litellm.acompletion", new=AsyncMock()) as call:
                with pytest.raises(LLMBudgetExceeded):
                    await client.complete("m", [{"role": "user", "content": "x"}])
            call.assert_not_awaited()  # tripped BEFORE spending anything further

    async def test_allows_call_under_budget(self):
        client = LLMClient()
        with (
            patch.object(settings, "llm_run_budget_usd", 5.0),
            patch.object(settings, "llm_cost_per_1m_tokens_usd", 1.0),
        ):
            client._completion_tokens = 1_000_000  # $1.00 < $5.00
            with patch("engine.llm.client.litellm.acompletion", new=AsyncMock(return_value=_ok())):
                out = await client.complete("m", [{"role": "user", "content": "x"}])
        assert out == '{"ok": true}'

    async def test_budget_zero_disables_the_guard(self):
        client = LLMClient()
        with (
            patch.object(settings, "llm_run_budget_usd", 0.0),
            patch.object(settings, "llm_cost_per_1m_tokens_usd", 1.0),
        ):
            client._completion_tokens = 999_000_000  # enormous, but the guard is off
            with patch("engine.llm.client.litellm.acompletion", new=AsyncMock(return_value=_ok())):
                out = await client.complete("m", [{"role": "user", "content": "x"}])
        assert out == '{"ok": true}'

    async def test_budget_exceeded_is_an_llmerror_subclass(self):
        # So the caller's existing LLM-failure degrade path handles it without new plumbing.
        from engine.llm.client import LLMError
        assert issubclass(LLMBudgetExceeded, LLMError)
