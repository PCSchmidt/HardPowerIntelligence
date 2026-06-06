import json
from engine.brief.rag import PassageContext


def build_synthesis_prompt(
    desk: str,
    passages: list[PassageContext],
    verified_facts: list[dict],
    max_items: int,
) -> list[dict]:
    facts_block = json.dumps(verified_facts, indent=2) if verified_facts else "[]"

    passages_block = "\n".join(
        f"[{p.index}] {p.source_id} ({p.fetched_at.strftime('%Y-%m-%d')}) "
        f"<{p.url}>\n\"{p.excerpt}\""
        for p in passages
    )

    schema = json.dumps({
        "headline": "string — one-line brief title",
        "bluf": "string — 2–3 sentence bottom-line-up-front summary",
        "items": [
            {
                "item_type": "award|filing|policy|macro|signal",
                "headline": "string",
                "body": "string — prose with [CITE:N] inline citations. Every sentence must end with at least one [CITE:N].",
                "entity_mentions": ["entity name strings"],
                "citation_indices": ["integer indices of passages cited"],
            }
        ],
    }, indent=2)

    system = (
        f"You are a senior Defense intelligence analyst producing the daily {desk.upper()} desk brief. "
        "Write in a precise, factual BLUF style. Every factual claim must cite its source using [CITE:N] "
        "where N is the passage index. Do not invent facts not supported by the provided passages. "
        "Return only valid JSON matching the output schema."
    )

    user = f"""## Verified facts (ground truth — do not contradict or modify)
{facts_block}

## Source passages (cite by index number)
{passages_block}

## Output schema
{schema}

## Instructions
Generate a {desk.upper()} desk BLUF brief with {max_items} items maximum (target 2–3 given the passage count).
Prioritize high-dollar contract awards, significant filings, and policy developments.

CRITICAL CITATION RULE: Every single sentence in every item body MUST end with [CITE:N].
If a sentence does not have [CITE:N] at the end, it will be automatically failed by the evaluation system.
Only write sentences you can directly support with a provided passage. Do not add context, background,
or analysis that is not in the passages. One sentence per item is better than two sentences where one is uncited."""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
