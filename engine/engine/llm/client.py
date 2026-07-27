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

# Errors that mean "OpenRouter couldn't serve this call" and so justify failing over to the
# cross-provider last-resort (D158): the retryable/availability set above, plus auth/permission
# walls (401/403). Deliberately NOT generic Exception — a ValueError/BadRequest is a request-shape
# bug the last resort can't fix, so those propagate immediately instead of wasting a Fireworks call.
_PROVIDER_OUTAGE_ERRORS = _RETRYABLE_ERRORS + tuple(
    exc
    for exc in (
        getattr(litellm, name, None)
        for name in ("AuthenticationError", "PermissionDeniedError")
    )
    if isinstance(exc, type)
)

# LiteLLM reads credentials from os.environ, not from our Settings object.
# Ensure they're present before any API call is made.
if settings.openrouter_api_key:
    os.environ.setdefault("OPENROUTER_API_KEY", settings.openrouter_api_key)
if settings.anthropic_api_key:
    os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
if settings.fireworks_api_key:
    # litellm's fireworks_ai provider reads FIREWORKS_AI_API_KEY; set the vendor's own
    # FIREWORKS_API_KEY too so either lookup path resolves the cross-provider fallback lane.
    os.environ.setdefault("FIREWORKS_AI_API_KEY", settings.fireworks_api_key)
    os.environ.setdefault("FIREWORKS_API_KEY", settings.fireworks_api_key)

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```")

# Auth/credit failures — 401 (unauthorized), 402 (payment-required), 403 (key-limit/forbidden)
# — are PERMANENT for this provider within a run, not a transient blip. Retrying with backoff
# can't clear them: it only burns wall-clock (a credit-exhausted run retried the billing wall
# for 6+ minutes on 2026-07-24) and, if any credit remains, spends more of it. Treat them as
# terminal so control returns immediately to the next fallback / provider instead of looping.
_TERMINAL_STATUS = {401, 402, 403}


def _is_terminal_provider_error(exc: Exception) -> bool:
    code = getattr(exc, "status_code", None)
    try:
        return int(code) in _TERMINAL_STATUS
    except (TypeError, ValueError):
        return False


def _is_credit_exhaustion_error(exc: Exception) -> bool:
    """A 402 — the OpenRouter *account* balance hit $0 ("requires more credits", D158).

    Distinct from 401/403 (bad key / key-limit cap): the account auto-refills within a couple of
    minutes, so a 402 DOES clear on a wait, whereas 401/403 never do. This is the one billing wall
    worth sleeping through instead of failing over immediately."""
    try:
        return int(getattr(exc, "status_code", None)) == 402
    except (TypeError, ValueError):
        return False


def resolve_fallbacks(primary: list[str] | None) -> list[str] | None:
    """Clean a call's **OpenRouter** fallback chain (dedup, drop falsy, None-safe).

    NOTE (D158): the cross-provider last-resort is **no longer appended here**. ``complete()`` now
    applies it as an explicit *second phase*, reached only after the OpenRouter phase — including a
    long refill-wait retry on a 402 (`llm_credit_refill_*`) — is exhausted. Keeping Fireworks out of
    this chain is what stops a routine OpenRouter credit blip from immediately spending (and slowly
    draining) the separate-billing emergency reserve: blips wait for the account auto-refill and stay
    on OpenRouter; Fireworks fires only on a genuine outage."""
    chain: list[str] = []
    for m in (primary or []):
        if m and m not in chain:
            chain.append(m)
    return chain or None


class LLMError(Exception):
    pass


def parse_json(text: str | None) -> dict | list | None:
    """Return parsed JSON from text, stripping markdown fences if present.

    None-safe: a provider can return null content (finish_reason='error'); treat it as
    unparseable rather than crashing on ``None.strip()`` (darkened the Defense desk, D128)."""
    text = (text or "").strip()
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
        """Call litellm with exponential backoff + jitter on transient errors (D076, D158).

        A rate-limit (429) is a time window, so an immediate re-try just hits the same
        wall; we sleep with doubling backoff (plus jitter to de-sync the three desks)
        so the window passes. A 402 (account credits at $0) is special: this account
        auto-refills within minutes, so we sleep ~2.5 min and retry on OpenRouter up to
        `llm_credit_refill_retries` times before giving up (D158) — staying on the cheaper
        primary and preserving the Fireworks reserve. 401/403 stay terminal (a wait never
        clears a bad key or a key-limit cap). Other non-retryable errors propagate immediately."""
        last_exc: Exception | None = None
        refill_waits = 0
        attempt = 0
        while True:
            try:
                return await litellm.acompletion(**kwargs)
            except _RETRYABLE_ERRORS as exc:
                last_exc = exc
                # 402: account balance hit $0. Auto-refill clears it in ~minutes, so wait it out
                # and retry on OpenRouter rather than fail over to the pricier last-resort (D158).
                if _is_credit_exhaustion_error(exc) and refill_waits < settings.llm_credit_refill_retries:
                    refill_waits += 1
                    delay = settings.llm_credit_refill_wait_seconds
                    log.warning(
                        "llm_credit_refill_wait",
                        model=kwargs.get("model"),
                        attempt=refill_waits,
                        max_attempts=settings.llm_credit_refill_retries,
                        wait=round(delay, 1),
                        error=str(exc)[:200],
                    )
                    await asyncio.sleep(delay)
                    continue
                # A billing/auth wall (401/403, or a 402 whose refill-waits are spent) is terminal
                # for this provider — hand control to the caller's last-resort phase, don't loop.
                if _is_terminal_provider_error(exc) or attempt >= settings.llm_max_retries:
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
                attempt += 1
        assert last_exc is not None  # only reached after a retryable failure
        raise last_exc

    def _last_resort_model(self, already: list[str]) -> str | None:
        """The cross-provider last-resort, unless it's already one of the models tried."""
        lr = settings.llm_model_fallback_last_resort
        return lr if (lr and lr not in already) else None

    async def _complete_openrouter_then_last_resort(self, base: dict, or_fallbacks: list[str]):
        """Two-phase completion (D158). Phase 1: OpenRouter — the primary plus its OpenRouter
        fallbacks, run through the retry loop (which waits out a 402 for the account auto-refill).
        Phase 2: the cross-provider last-resort (Fireworks, separate billing) — reached ONLY once
        the whole OpenRouter phase is exhausted, so routine credit blips stay on OpenRouter and the
        emergency reserve isn't drained. Returns (served_model, response)."""
        kwargs = dict(base)
        if or_fallbacks:
            kwargs["fallbacks"] = or_fallbacks
        try:
            return base["model"], await self._acompletion_with_retry(**kwargs)
        except _PROVIDER_OUTAGE_ERRORS as exc:  # OpenRouter couldn't serve → try the last resort
            last_resort = self._last_resort_model([base["model"], *or_fallbacks])
            if last_resort is None:
                raise
            log.warning(
                "llm_last_resort_engaged",
                primary=base["model"],
                last_resort=last_resort,
                error=str(exc)[:200],
            )
            lr_kwargs = dict(base)  # no fallbacks, no refill-wait — a separate provider/billing
            lr_kwargs["model"] = last_resort
            return last_resort, await self._acompletion_with_retry(**lr_kwargs)

    async def complete(
        self,
        model: str,
        messages: list[dict],
        json_mode: bool = True,
        fallbacks: list[str] | None = None,
        temperature: float | None = None,
    ) -> str:
        base: dict = {"model": model, "messages": messages}
        if json_mode:
            base["response_format"] = {"type": "json_object"}
        if temperature is not None:
            base["temperature"] = temperature

        or_fallbacks = fallbacks or []
        served_model, response = await self._complete_openrouter_then_last_resort(base, or_fallbacks)
        content = response.choices[0].message.content
        self._record_usage(served_model, response)

        # A provider-side error can return finish_reason='error' with NULL content and NO
        # exception — so litellm's own `fallbacks` never fire, and the None crashes downstream
        # (`'NoneType' has no attribute 'strip'` darkened the Defense desk 2026-07-06, D128). This
        # hits the largest desk first: a bigger synthesis prompt is likelier to trip the provider.
        # Treat empty content as a failure: walk the OpenRouter fallbacks and then the last-resort
        # explicitly (D158), then raise a clean LLMError the caller's re-roll (D072) can handle.
        if not content:
            log.warning("llm_empty_content", model=served_model, fallbacks=or_fallbacks)
            empty_chain = list(or_fallbacks)
            lr = self._last_resort_model([model, *or_fallbacks])
            if lr is not None:
                empty_chain.append(lr)
            for fb in empty_chain:
                fb_kwargs = dict(base)
                fb_kwargs["model"] = fb
                response = await self._acompletion_with_retry(**fb_kwargs)
                content = response.choices[0].message.content
                self._record_usage(fb, response)
                if content:
                    served_model = fb
                    break
            if not content:
                raise LLMError(
                    f"Empty content from model={model} and fallbacks "
                    f"{empty_chain} (provider finish_reason=error?)"
                )

        if json_mode:
            if parse_json(content) is None:
                # One repair retry, on whichever model actually served the content.
                repair_messages = messages + [
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": "Your response was not valid JSON. Return only valid JSON, no other text."},
                ]
                repair_kwargs = dict(base)
                repair_kwargs["model"] = served_model
                repair_kwargs["messages"] = repair_messages
                response = await self._acompletion_with_retry(**repair_kwargs)
                content = response.choices[0].message.content
                self._record_usage(served_model, response)
                if parse_json(content) is None:
                    raise LLMError(f"JSON parse failed after repair retry for model={served_model}")

        return content


# Module-level singleton — imported by generator and eval
llm_client = LLMClient()
