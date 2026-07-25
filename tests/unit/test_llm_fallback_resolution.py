"""Cross-provider last-resort wiring (2026-07-24 dark).

The whole OpenRouter waterfall shares one billing balance, so credit exhaustion (402/403)
403s every tier at once and the site goes stale. Two defenses are unit-tested here:

  1. resolve_fallbacks() appends a SEPARATE-account last-resort to every chain, so a dead
     OpenRouter account degrades to a pricier brief instead of no brief.
  2. _is_terminal_provider_error() makes 401/402/403 fail over immediately instead of
     retrying the billing wall with backoff (which burned 6+ minutes on 7/24).
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import litellm
import pytest

from engine.llm.client import (
    LLMClient,
    _is_terminal_provider_error,
    resolve_fallbacks,
)
from engine.settings import settings

_LAST_RESORT = "fireworks_ai/accounts/fireworks/models/deepseek-v4-pro"


def _ok(content='{"ok": true}'):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )


class TestResolveFallbacks:
    def test_appends_last_resort_to_a_primary_chain(self):
        assert resolve_fallbacks(["openrouter/qwen/qwen3.7-max"]) == [
            "openrouter/qwen/qwen3.7-max",
            settings.llm_model_fallback_last_resort,
        ]

    def test_last_resort_is_a_separate_provider_from_openrouter(self):
        # The whole point: the last-resort must NOT be an openrouter/ model, or it shares
        # the dead account and provides zero resilience against the outage we're fixing.
        assert not settings.llm_model_fallback_last_resort.startswith("openrouter/")

    def test_none_primary_yields_last_resort_only(self):
        # The analysis reground call had NO fallback before — now it gets the escape hatch.
        assert resolve_fallbacks(None) == [settings.llm_model_fallback_last_resort]

    def test_empty_entries_are_dropped(self):
        assert resolve_fallbacks([""]) == [settings.llm_model_fallback_last_resort]

    def test_no_duplicate_when_primary_already_is_last_resort(self):
        lr = settings.llm_model_fallback_last_resort
        assert resolve_fallbacks([lr]) == [lr]

    def test_returns_none_only_when_nothing_to_offer(self):
        with patch.object(settings, "llm_model_fallback_last_resort", ""):
            assert resolve_fallbacks(None) is None
            assert resolve_fallbacks([""]) is None


class TestTerminalErrorClassification:
    @pytest.mark.parametrize("code", [401, 402, 403])
    def test_auth_and_billing_codes_are_terminal(self, code):
        assert _is_terminal_provider_error(SimpleNamespace(status_code=code)) is True

    @pytest.mark.parametrize("code", [429, 500, 529])
    def test_transient_codes_are_not_terminal(self, code):
        assert _is_terminal_provider_error(SimpleNamespace(status_code=code)) is False

    def test_missing_or_nonnumeric_status_is_not_terminal(self):
        assert _is_terminal_provider_error(SimpleNamespace()) is False
        assert _is_terminal_provider_error(SimpleNamespace(status_code=None)) is False
        assert _is_terminal_provider_error(SimpleNamespace(status_code="oops")) is False

    def test_string_status_code_is_coerced(self):
        # litellm occasionally carries status_code as a string.
        assert _is_terminal_provider_error(SimpleNamespace(status_code="402")) is True


@pytest.mark.asyncio
class TestTerminalFastFail:
    async def test_billing_error_does_not_retry_with_backoff(self):
        # A 402 is the credit wall — retrying can't clear it, so bail on the first hit
        # instead of sleeping through the full backoff budget.
        billing = litellm.APIError(
            status_code=402, message="requires more credits",
            llm_provider="openrouter", model="x",
        )
        with (
            patch("engine.llm.client.litellm.acompletion", new=AsyncMock(side_effect=billing)) as call,
            patch("engine.llm.client.asyncio.sleep", new=AsyncMock()) as sleep,
            patch("engine.llm.client.settings.llm_max_retries", 4),
        ):
            client = LLMClient()
            with pytest.raises(litellm.APIError):
                await client.complete("openrouter/deepseek/deepseek-v4-pro",
                                      [{"role": "user", "content": "x"}])
        assert call.call_count == 1        # no retries on the billing wall
        sleep.assert_not_awaited()         # no backoff burned

    async def test_rate_limit_still_retries(self):
        # Guard against over-reach: a 429 is a time window, not a wall — keep retrying it.
        rl = litellm.RateLimitError(message="429", llm_provider="openrouter", model="x")
        with (
            patch("engine.llm.client.litellm.acompletion",
                  new=AsyncMock(side_effect=[rl, rl, _ok()])) as call,
            patch("engine.llm.client.asyncio.sleep", new=AsyncMock()),
        ):
            client = LLMClient()
            out = await client.complete("openrouter/qwen/qwen3.7-max",
                                        [{"role": "user", "content": "x"}])
        assert out == '{"ok": true}'
        assert call.call_count == 3
