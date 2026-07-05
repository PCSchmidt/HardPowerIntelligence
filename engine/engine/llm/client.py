import asyncio
import json
import os
import random
import re

import litellm
import structlog

from engine.settings import settings

log = structlog.get_logger()

# Transient provider failures worth a delay-and-retry (D076). The 06-17 outage was a
# litellm.RateLimitError (OpenRouter 429) and a litellm.APIError (deepseek non-JSON);
# both are retryable. Built defensively so a litellm version that drops one of these
# names doesn't break import.
_RETRYABLE_ERRORS = tuple(
    exc
    for exc in (
        getattr(litellm, name, None)
        for name in (
            "RateLimitError",
            "APIConnectionError",
            "Timeout",
            "ServiceUnavailableError",
            "InternalServerError",
            "APIError",
        )
    )
    if isinstance(exc, type)
)

# LiteLLM reads credentials from os.environ, not from our Settings object.
# Ensure they're present before any API call is made.
if settings.openrouter_api_key:
    os.environ.setdefault("OPENROUTER_API_KEY", settings.openrouter_api_key)
if settings.anthropic_api_key:
    os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```")


class LLMError(Exception):
    pass


def parse_json(text: str) -> dict | list | None:
    """Return parsed JSON from text, stripping markdown fences if present."""
    text = text.strip()
    fence = _FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


class LLMClient:
    """Wraps litellm with retry/backoff and a process-level token accumulator (A4).

    Each desk's brief runs in its own process (the CI matrix), so the singleton's counters
    naturally scope to one desk-run: `usage_snapshot()` at the end reports that desk's total
    LLM spend. Covers completion calls only — embeddings go through a separate OpenAI path."""

    def __init__(self) -> None:
        self._calls = 0
        self._prompt_tokens = 0
        self._completion_tokens = 0

    def reset_usage(self) -> None:
        self._calls = self._prompt_tokens = self._completion_tokens = 0

    def usage_snapshot(self) -> dict:
        """Cumulative token usage since process start (or last reset) + an APPROXIMATE cost.

        Token counts are the real signal; the dollar figure is a coarse blended estimate (the
        pipeline mixes models), useful only for eyeballing anomalies — never billing."""
        total = self._prompt_tokens + self._completion_tokens
        return {
            "calls": self._calls,
            "prompt_tokens": self._prompt_tokens,
            "completion_tokens": self._completion_tokens,
            "total_tokens": total,
            "est_cost_usd": round(total / 1_000_000 * settings.llm_cost_per_1m_tokens_usd, 4),
        }

    def _record_usage(self, model: str, response) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        pt = getattr(usage, "prompt_tokens", 0) or 0
        ct = getattr(usage, "completion_tokens", 0) or 0
        self._calls += 1
        self._prompt_tokens += pt
        self._completion_tokens += ct
        log.info("llm_call", model=model, prompt_tokens=pt, completion_tokens=ct)

    async def _acompletion_with_retry(self, **kwargs):
        """Call litellm with exponential backoff + jitter on transient errors (D076).

        A rate-limit (429) is a time window, so an immediate re-try just hits the same
        wall; we sleep with doubling backoff (plus jitter to de-sync the three desks)
        so the window passes. Non-retryable errors propagate immediately."""
        last_exc: Exception | None = None
        for attempt in range(settings.llm_max_retries + 1):
            try:
                return await litellm.acompletion(**kwargs)
            except _RETRYABLE_ERRORS as exc:
                last_exc = exc
                if attempt >= settings.llm_max_retries:
                    break
                delay = min(
                    settings.llm_backoff_base_seconds * (2 ** attempt),
                    settings.llm_backoff_max_seconds,
                )
                delay += random.uniform(0, delay * 0.25)  # jitter
                log.warning(
                    "llm_retry",
                    model=kwargs.get("model"),
                    attempt=attempt + 1,
                    max_attempts=settings.llm_max_retries + 1,
                    delay=round(delay, 1),
                    error=str(exc)[:200],
                )
                await asyncio.sleep(delay)
        assert last_exc is not None  # only reached after a retryable failure
        raise last_exc

    async def complete(
        self,
        model: str,
        messages: list[dict],
        json_mode: bool = True,
        fallbacks: list[str] | None = None,
        temperature: float | None = None,
    ) -> str:
        kwargs: dict = {"model": model, "messages": messages}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if fallbacks:
            kwargs["fallbacks"] = fallbacks
        if temperature is not None:
            kwargs["temperature"] = temperature

        response = await self._acompletion_with_retry(**kwargs)
        content = response.choices[0].message.content
        self._record_usage(model, response)

        if json_mode:
            if parse_json(content) is None:
                # One repair retry
                repair_messages = messages + [
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": "Your response was not valid JSON. Return only valid JSON, no other text."},
                ]
                repair_kwargs = {**kwargs, "messages": repair_messages}
                response = await self._acompletion_with_retry(**repair_kwargs)
                content = response.choices[0].message.content
                self._record_usage(model, response)
                if parse_json(content) is None:
                    raise LLMError(f"JSON parse failed after repair retry for model={model}")

        return content


# Module-level singleton — imported by generator and eval
llm_client = LLMClient()
