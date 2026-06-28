import json
from engine.brief.rag import PassageContext

# Desk-aware analyst persona (D060 multi-desk). The brief covers three desks, so the
# persona must match the desk — not a hardcoded "Defense" one.
_DESK_PERSONA = {
    "defense": "defense-technology",
    "ai": "artificial-intelligence",
    "energy": "energy-technology",
}


def build_synthesis_prompt(
    desk: str,
    passages: list[PassageContext],
    verified_facts: list[dict],
    max_items: int,
) -> list[dict]:
    facts_block = json.dumps(verified_facts, indent=2) if verified_facts else "[]"
    persona = _DESK_PERSONA.get(desk, desk)

    passages_block = "\n".join(
        f"[{p.index}] {p.source_id} ({p.fetched_at.strftime('%Y-%m-%d')}) "
        f"<{p.url}>\n\"{p.excerpt}\""
        for p in passages
    )

    schema = json.dumps({
        "headline": "string — one-line brief title",
        "bluf": (
            "string — a 4–6 sentence bottom-line-up-front NARRATIVE on the state of the "
            "desk's domain today: the most important developments, the through-line "
            "connecting them, and what it means for the reader. A real summary an analyst "
            "would lead with, not a one-line teaser. ANALYSIS — no [CITE:N] required."
        ),
        "convergence_read": (
            "string — cross-signal thesis tying the day's items together, especially "
            "Defense/AI/Energy overlaps. ANALYSIS, not new facts; no citations required. "
            "Empty string if there is no genuine through-line."
        ),
        "items": [
            {
                "item_type": "award|filing|policy|macro|signal",
                "headline": "string",
                "body": (
                    "string — the VERIFIABLE FACT as prose with [CITE:N] inline citations. "
                    "Every sentence must end with at least one [CITE:N]."
                ),
                "read": (
                    "string — ANALYSIS: why this is material, second-order effects, who is "
                    "exposed, comparables. Grounded in the facts + domain knowledge; introduce "
                    "NO new concrete facts (numbers, names, dates, events) and NO [CITE:N]. "
                    "No buy/sell advice."
                ),
                "watch": (
                    "string — optional forward hook: the next catalyst, or a confirming/"
                    "disconfirming signal to watch. Same grounding rules. Empty string if none."
                ),
                "entity_mentions": ["entity name strings"],
                "citation_indices": ["integer indices of passages cited"],
            }
        ],
    }, indent=2)

    system = (
        f"You are a senior {persona} intelligence analyst producing the daily {desk.upper()} desk brief. "
        f"Your job is a COMPREHENSIVE read of the {desk.upper()} domain — cover every genuinely material "
        "development the facts support, not just the top few. Each item has two layers: a `body` of "
        "VERIFIABLE FACTS where every sentence cites its source with [CITE:N], and a `read` (plus optional "
        "`watch`) of ANALYSIS — your interpretation of why the facts matter, what they imply, and what to "
        "watch. The analysis may interpret and look forward but must stay grounded in the facts: introduce "
        "no new concrete fact (number, name, date, event) and give no buy/sell advice. Do not invent facts "
        f"not supported by the provided passages. DESK DISCIPLINE: include only developments that genuinely "
        f"belong on the {desk.upper()} desk; if a development's center of gravity is another desk, leave it "
        "out. Return only valid JSON matching the output schema."
    )

    user = f"""## Verified facts (ground truth — do not contradict or modify)
{facts_block}

## Source passages (cite by index number)
{passages_block}

## Output schema
{schema}

## Instructions
Generate a comprehensive {desk.upper()} desk BLUF brief. Write ONE substantive item for each genuinely
material development the facts support, up to {max_items} items. Aim to cover the domain thoroughly — do
NOT stop at two or three if the facts support more. But quality over quota: never pad, never split one
development into multiple items, never duplicate, and never manufacture an item the passages don't support.
If the material is thin, write fewer strong items rather than weak filler. Cover the full range that belongs
on this desk — contract awards, significant filings, regulatory and policy moves, research and technology
milestones, and notable corporate or market developments — not only the highest-dollar awards.

CRITICAL CITATION RULE (applies to `body` only): Every single sentence in every item `body` MUST end with
[CITE:N]. If a body sentence has no [CITE:N], it is automatically dropped by the evaluation system.
Only write body sentences you can directly support with a provided passage.

ANALYSIS LAYER (`read`, `watch`, `convergence_read`): this is your interpretation, so it does NOT carry
[CITE:N]. Say why the facts matter, the second-order implications, who is exposed, and what to watch next —
as a decisioning lens, never buy/sell advice. It must stay grounded in the facts above: do not assert any
new number, name, date, or event that is not in the facts. Leave a field as an empty string rather than
padding it with fabrication."""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
