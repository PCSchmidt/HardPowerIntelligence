"""
Tests for engine/llm/client.py (D037).
All tests mock litellm — no network calls.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine.llm.client import LLMClient, LLMError


class TestComplete:
    @pytest.mark.asyncio
    async def test_returns_content_string(self):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"result": "ok"}'
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 20

        with patch("engine.llm.client.litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            client = LLMClient()
            result = await client.complete(
                model="openrouter/deepseek/deepseek-v4-pro",
                messages=[{"role": "user", "content": "test"}],
            )
        assert result == '{"result": "ok"}'

    @pytest.mark.asyncio
    async def test_json_mode_enforced_by_default(self):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"ok": true}'
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 10

        with patch("engine.llm.client.litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            client = LLMClient()
            await client.complete(
                model="openrouter/qwen/qwen3.7-max",
                messages=[{"role": "user", "content": "test"}],
            )
        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs.get("response_format") == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_json_mode_disabled_when_requested(self):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "plain text response"
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 10

        with patch("engine.llm.client.litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            client = LLMClient()
            await client.complete(
                model="openrouter/deepseek/deepseek-v4-pro",
                messages=[{"role": "user", "content": "test"}],
                json_mode=False,
            )
        call_kwargs = mock_call.call_args.kwargs
        assert "response_format" not in call_kwargs

    @pytest.mark.asyncio
    async def test_repair_retry_on_invalid_json(self):
        bad_response = MagicMock()
        bad_response.choices[0].message.content = "not valid json {"
        bad_response.usage.prompt_tokens = 50
        bad_response.usage.completion_tokens = 5

        good_response = MagicMock()
        good_response.choices[0].message.content = '{"fixed": true}'
        good_response.usage.prompt_tokens = 60
        good_response.usage.completion_tokens = 10

        with patch(
            "engine.llm.client.litellm.acompletion",
            new=AsyncMock(side_effect=[bad_response, good_response]),
        ):
            client = LLMClient()
            result = await client.complete(
                model="openrouter/deepseek/deepseek-v4-pro",
                messages=[{"role": "user", "content": "test"}],
            )
        assert result == '{"fixed": true}'

    @pytest.mark.asyncio
    async def test_raises_llm_error_after_two_json_failures(self):
        bad_response = MagicMock()
        bad_response.choices[0].message.content = "still not json"
        bad_response.usage.prompt_tokens = 50
        bad_response.usage.completion_tokens = 5

        with patch(
            "engine.llm.client.litellm.acompletion",
            new=AsyncMock(return_value=bad_response),
        ):
            client = LLMClient()
            with pytest.raises(LLMError, match="JSON"):
                await client.complete(
                    model="openrouter/deepseek/deepseek-v4-pro",
                    messages=[{"role": "user", "content": "test"}],
                )

    @pytest.mark.asyncio
    async def test_temperature_passed_when_set(self):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"ok": true}'
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 10

        with patch("engine.llm.client.litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            client = LLMClient()
            await client.complete(
                model="openrouter/deepseek/deepseek-v4-pro",
                messages=[{"role": "user", "content": "test"}],
                temperature=0.0,
            )
        assert mock_call.call_args.kwargs.get("temperature") == 0.0

    @pytest.mark.asyncio
    async def test_temperature_omitted_when_none(self):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"ok": true}'
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 10

        with patch("engine.llm.client.litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            client = LLMClient()
            await client.complete(
                model="openrouter/deepseek/deepseek-v4-pro",
                messages=[{"role": "user", "content": "test"}],
            )
        assert "temperature" not in mock_call.call_args.kwargs

    @pytest.mark.asyncio
    async def test_fallbacks_passed_to_litellm(self):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"ok": true}'
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 10

        with patch("engine.llm.client.litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            client = LLMClient()
            await client.complete(
                model="openrouter/deepseek/deepseek-v4-pro",
                messages=[{"role": "user", "content": "test"}],
                fallbacks=["openrouter/qwen/qwen3.7-max"],
            )
        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs.get("fallbacks") == ["openrouter/qwen/qwen3.7-max"]


class TestMaterialize:
    def test_parse_valid_json(self):
        from engine.llm.client import parse_json
        result = parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_with_markdown_fence(self):
        from engine.llm.client import parse_json
        result = parse_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_parse_invalid_json_returns_none(self):
        from engine.llm.client import parse_json
        result = parse_json("not json at all")
        assert result is None
