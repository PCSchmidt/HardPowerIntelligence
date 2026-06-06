import json
import re

import litellm
import structlog

log = structlog.get_logger()

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
    async def complete(
        self,
        model: str,
        messages: list[dict],
        json_mode: bool = True,
        fallbacks: list[str] | None = None,
    ) -> str:
        kwargs: dict = {"model": model, "messages": messages}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if fallbacks:
            kwargs["fallbacks"] = fallbacks

        response = await litellm.acompletion(**kwargs)
        content = response.choices[0].message.content

        usage = response.usage
        log.info(
            "llm_call",
            model=model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
        )

        if json_mode:
            if parse_json(content) is None:
                # One repair retry
                repair_messages = messages + [
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": "Your response was not valid JSON. Return only valid JSON, no other text."},
                ]
                repair_kwargs = {**kwargs, "messages": repair_messages}
                response = await litellm.acompletion(**repair_kwargs)
                content = response.choices[0].message.content
                if parse_json(content) is None:
                    raise LLMError(f"JSON parse failed after repair retry for model={model}")

        return content


# Module-level singleton — imported by generator and eval
llm_client = LLMClient()
