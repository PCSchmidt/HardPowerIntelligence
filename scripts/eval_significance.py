"""Strategic-significance curation eval (D085 tuning) — operator-run; spends a little LLM.

The significance gate's threshold logic is unit-tested, but its *judgment* (the LLM prompt) is not —
and that judgment is what decides whether SPAC/shell froth gets dropped and real deals get kept. This
runs the real triage over a labeled golden set (tests/fixtures/significance_golden.json), per desk, and
reports keep/drop vs expected so the prompt can be tuned measurably rather than by eyeballing one brief.

Advisory (not CI-wired): LLM judgment varies run-to-run; this is a tuning/validation tool. Run after
editing the significance prompt:

    uv run python scripts/eval_significance.py
"""
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

from engine.brief.significance import _score_facts
from engine.settings import settings

_GOLDEN = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "significance_golden.json"
_PASS_BAR = 0.85  # advisory


async def main() -> int:
    items = json.loads(_GOLDEN.read_text(encoding="utf-8"))["items"]
    threshold = settings.significance_threshold

    by_desk: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_desk[it["desk"]].append(it)

    correct = 0
    froth_total = froth_caught = signal_total = signal_kept = 0
    print(f"Significance eval — threshold={threshold} model={settings.significance_model or settings.llm_model_eval}\n")

    for desk, desk_items in by_desk.items():
        facts = [({"text_chunk": it["text"]}, 0.5) for it in desk_items]
        scores = await _score_facts(facts, desk)
        print(f"=== {desk} ===")
        for i, it in enumerate(desk_items):
            score, reason = scores.get(i, (1.0, "unscored(fail-open)"))
            action = "keep" if score >= threshold else "drop"
            ok = action == it["expected"]
            correct += ok
            if it["expected"] == "drop":
                froth_total += 1
                froth_caught += action == "drop"
            else:
                signal_total += 1
                signal_kept += action == "keep"
            mark = "ok" if ok else "XX"
            print(f"  {mark} exp={it['expected']:4} got={action:4} score={score:.2f}  {it['note']}")
            if not ok:
                print(f"       └ model reason: {reason!r}")
        print()

    total = len(items)
    acc = correct / total if total else 0.0
    print(f"Accuracy: {correct}/{total} = {acc:.2f}")
    print(f"Froth caught (should-drop dropped): {froth_caught}/{froth_total}")
    print(f"Signal kept  (should-keep kept):    {signal_kept}/{signal_total}")
    verdict = "PASS" if acc >= _PASS_BAR else "REVIEW"
    print(f"\n{verdict}: accuracy {acc:.2f} vs advisory bar {_PASS_BAR}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
