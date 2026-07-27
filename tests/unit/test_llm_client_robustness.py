"""LLM client robustness to null provider content (D128).

A provider can return finish_reason='error' with null content and NO exception, so litellm's
own fallbacks don't fire. The client must not crash on the None (it darkened the Defense desk
2026-07-06); it should try the fallback model, then raise a clean LLMError the re-roll handles.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from engine.llm.client import LLMClient, LLMError, parse_json


def _resp(content):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )


class TestParseJsonNoneSafe:
    def test_none_returns_none_not_crash(self):
        assert parse_json(None) is None

    def test_empty_returns_none(self):
        assert parse_json("") is None

    def test_valid_json_still_parses(self):
        assert parse_json('{"a": 1}') == {"a": 1}


@pytest.mark.asyncio
class TestEmptyContentHandling:
    async def test_falls_back_to_secondary_model_on_null_content(self):
        c = LLMClient()
        # Primary returns null content; fallback returns valid content.
        c._acompletion_with_retry = AsyncMock(side_effect=[_resp(None), _resp('{"ok": true}')])
        out = await c.complete("primary", [{"role": "user", "content": "x"}],
                               fallbacks=["fallback"])
        assert out == '{"ok": true}'
        assert c._acompletion_with_retry.call_count == 2

    async def test_empty_content_falls_through_to_last_resort(self):
        # D158: on null content the explicit chain now also tries the cross-provider last-resort,
        # so an empty OpenRouter reply degrades to a Fireworks brief instead of raising.
        from engine.settings import settings
        c = LLMClient()
        c._acompletion_with_retry = AsyncMock(side_effect=[_resp(None), _resp('{"ok": true}')])
        out = await c.complete("primary", [{"role": "user", "content": "x"}])  # no OR fallbacks
        assert out == '{"ok": true}'
        assert c._acompletion_with_retry.call_count == 2
        assert c._acompletion_with_retry.await_args.kwargs["model"] == settings.llm_model_fallback_last_resort

    async def test_raises_clean_error_when_all_empty(self):
        c = LLMClient()
        # primary + OR fallback + last-resort all empty (D158) → 3 attempts, then a clean raise.
        c._acompletion_with_retry = AsyncMock(side_effect=[_resp(None), _resp(None), _resp(None)])
        with pytest.raises(LLMError):
            await c.complete("primary", [{"role": "user", "content": "x"}],
                             fallbacks=["fallback"])
        assert c._acompletion_with_retry.call_count == 3

    async def test_raises_clean_error_with_no_fallbacks(self):
        c = LLMClient()
        # No OR fallbacks: primary + last-resort both empty → raise (not AttributeError).
        c._acompletion_with_retry = AsyncMock(side_effect=[_resp(None), _resp(None)])
        with pytest.raises(LLMError):
            await c.complete("primary", [{"role": "user", "content": "x"}], json_mode=True)

    async def test_normal_content_unaffected(self):
        c = LLMClient()
        c._acompletion_with_retry = AsyncMock(side_effect=[_resp('{"ok": 1}')])
        out = await c.complete("primary", [{"role": "user", "content": "x"}])
        assert out == '{"ok": 1}'
        assert c._acompletion_with_retry.call_count == 1
