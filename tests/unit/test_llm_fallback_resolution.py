"""Cross-provider last-resort + credit-refill wiring (2026-07-24 dark; D155/D158).

The whole OpenRouter waterfall shares one billing balance, so credit exhaustion 403s every tier
at once and the site goes stale. The defenses unit-tested here:

  1. resolve_fallbacks() builds the OpenRouter-only fallback chain (D158: the last-resort is NO
     longer appended here — complete() applies it as a separate second phase).
  2. complete() is two-phase: OpenRouter (primary + its fallbacks), then a SEPARATE-account
     last-resort (Fireworks) reached only once OpenRouter is exhausted — so a dead OpenRouter
     account degrades to a pricier brief instead of no brief, without draining the reserve on blips.
  3. A 402 (account credits at $0) waits ~2.5 min for the account auto-refill and retries on
     OpenRouter (D158); 401/403 (bad key / key-limit cap) stay terminal and fail over immediately.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import litellm
import pytest

from engine.llm.client import (
    LLMClient,
    _is_credit_exhaustion_error,
    _is_terminal_provider_error,
    resolve_fallbacks,
)
from engine.settings import settings


def _ok(content='{"ok": true}'):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )


def _billing(code: int):
    return litellm.APIError(
        status_code=code, message="requires more credits" if code == 402 else "key limit",
        llm_provider="openrouter", model="x",
    )


class TestResolveFallbacks:
    def test_returns_openrouter_chain_without_last_resort(self):
        # D158: the last-resort is applied by complete() as a second phase, NOT appended here —
        # so routine OpenRouter blips don't immediately spend the separate-billing reserve.
        assert resolve_fallbacks(["openrouter/qwen/qwen3.7-max"]) == ["openrouter/qwen/qwen3.7-max"]
        assert settings.llm_model_fallback_last_resort not in (
            resolve_fallbacks(["openrouter/qwen/qwen3.7-max"]) or []
        )

    def test_last_resort_is_a_separate_provider_from_openrouter(self):
        # The whole point: the last-resort must NOT be an openrouter/ model, or it shares
        # the dead account and provides zero resilience against the outage we're fixing.
        assert not settings.llm_model_fallback_last_resort.startswith("openrouter/")

    def test_none_and_empty_yield_none(self):
        assert resolve_fallbacks(None) is None
        assert resolve_fallbacks([]) is None
        assert resolve_fallbacks([""]) is None

    def test_dedupes_and_drops_falsy(self):
        assert resolve_fallbacks(["a", "", "a", "b"]) == ["a", "b"]


class TestErrorClassification:
    @pytest.mark.parametrize("code", [401, 402, 403])
    def test_auth_and_billing_codes_are_terminal(self, code):
        assert _is_terminal_provider_error(SimpleNamespace(status_code=code)) is True

    @pytest.mark.parametrize("code", [429, 500, 529])
    def test_transient_codes_are_not_terminal(self, code):
        assert _is_terminal_provider_error(SimpleNamespace(status_code=code)) is False

    def test_missing_or_nonnumeric_status_is_not_terminal(self):
        assert _is_terminal_provider_error(SimpleNamespace()) is False
        assert _is_terminal_provider_error(SimpleNamespace(status_code="oops")) is False

    def test_credit_exhaustion_is_402_only(self):
        assert _is_credit_exhaustion_error(SimpleNamespace(status_code=402)) is True
        assert _is_credit_exhaustion_error(SimpleNamespace(status_code="402")) is True  # coerced
        for code in (401, 403, 429, 500):
            assert _is_credit_exhaustion_error(SimpleNamespace(status_code=code)) is False
        assert _is_credit_exhaustion_error(SimpleNamespace()) is False


@pytest.mark.asyncio
class TestCreditRefillWait:
    async def test_402_waits_for_refill_then_succeeds_on_openrouter(self):
        # Account hit $0; auto-refill clears within minutes. We sleep the refill window, retry on
        # OpenRouter, and the retry succeeds — the Fireworks reserve is never touched.
        with (
            patch("engine.llm.client.litellm.acompletion",
                  new=AsyncMock(side_effect=[_billing(402), _ok()])) as call,
            patch("engine.llm.client.asyncio.sleep", new=AsyncMock()) as sleep,
            patch.object(settings, "llm_credit_refill_retries", 2),
            patch.object(settings, "llm_credit_refill_wait_seconds", 150.0),
        ):
            client = LLMClient()
            out = await client.complete("openrouter/deepseek/deepseek-v4-pro",
                                        [{"role": "user", "content": "x"}])
        assert out == '{"ok": true}'
        assert call.call_count == 2                       # one 402, one success — stayed on OpenRouter
        sleep.assert_awaited_once_with(150.0)             # waited the full refill window, not a backoff

    async def test_402_gives_up_after_configured_refill_retries(self):
        # If the refill never comes, bail after N long-waits (here last-resort disabled to isolate
        # the OpenRouter phase).
        with (
            patch("engine.llm.client.litellm.acompletion",
                  new=AsyncMock(side_effect=_billing(402))) as call,
            patch("engine.llm.client.asyncio.sleep", new=AsyncMock()) as sleep,
            patch.object(settings, "llm_credit_refill_retries", 2),
            patch.object(settings, "llm_model_fallback_last_resort", ""),
        ):
            client = LLMClient()
            with pytest.raises(litellm.APIError):
                await client.complete("openrouter/deepseek/deepseek-v4-pro",
                                      [{"role": "user", "content": "x"}])
        assert call.call_count == 3        # initial + 2 refill retries
        assert sleep.await_count == 2      # 2 refill waits, no backoff


@pytest.mark.asyncio
class TestTerminalFastFail:
    async def test_403_key_cap_fails_over_immediately_no_wait(self):
        # 403 (key-limit cap) never clears on a wait — isolate the OpenRouter phase (last-resort
        # disabled) and confirm it bails on the first hit with no sleep.
        with (
            patch("engine.llm.client.litellm.acompletion",
                  new=AsyncMock(side_effect=_billing(403))) as call,
            patch("engine.llm.client.asyncio.sleep", new=AsyncMock()) as sleep,
            patch.object(settings, "llm_model_fallback_last_resort", ""),
        ):
            client = LLMClient()
            with pytest.raises(litellm.APIError):
                await client.complete("openrouter/deepseek/deepseek-v4-pro",
                                      [{"role": "user", "content": "x"}])
        assert call.call_count == 1
        sleep.assert_not_awaited()

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


@pytest.mark.asyncio
class TestTwoPhaseLastResort:
    async def test_openrouter_403_falls_to_fireworks(self):
        # OpenRouter phase fully dead (403 key cap) → the separate-account last-resort serves.
        with (
            patch("engine.llm.client.litellm.acompletion",
                  new=AsyncMock(side_effect=[_billing(403), _ok()])) as call,
            patch("engine.llm.client.asyncio.sleep", new=AsyncMock()),
        ):
            client = LLMClient()
            out = await client.complete("openrouter/deepseek/deepseek-v4-pro",
                                        [{"role": "user", "content": "x"}])
        assert out == '{"ok": true}'
        assert call.call_count == 2   # OpenRouter (403) + Fireworks (ok)
        # the last-resort call used the Fireworks model, not an openrouter/ one
        assert call.await_args.kwargs["model"] == settings.llm_model_fallback_last_resort

    async def test_non_provider_error_does_not_trigger_last_resort(self):
        # A ValueError (request-shape bug, not a provider outage) must propagate immediately even
        # with the last-resort configured — Fireworks can't fix a bad request, so don't waste a call.
        with (
            patch("engine.llm.client.litellm.acompletion",
                  new=AsyncMock(side_effect=ValueError("boom"))) as call,
            patch("engine.llm.client.asyncio.sleep", new=AsyncMock()),
        ):
            client = LLMClient()
            with pytest.raises(ValueError, match="boom"):
                await client.complete("openrouter/deepseek/deepseek-v4-pro",
                                      [{"role": "user", "content": "x"}])
        assert call.call_count == 1   # no fail-over to Fireworks on a non-provider error

    async def test_last_resort_not_retried_when_already_in_chain(self):
        # If the last-resort somehow IS the primary, don't call it twice — just propagate.
        lr = settings.llm_model_fallback_last_resort
        with (
            patch("engine.llm.client.litellm.acompletion",
                  new=AsyncMock(side_effect=_billing(403))) as call,
            patch("engine.llm.client.asyncio.sleep", new=AsyncMock()),
        ):
            client = LLMClient()
            with pytest.raises(litellm.APIError):
                await client.complete(lr, [{"role": "user", "content": "x"}])
        assert call.call_count == 1   # no redundant second phase
