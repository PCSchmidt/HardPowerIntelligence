"""
Gate 5 integration run script (D042).
Generates a real brief from the local Supabase DB and records results.

Usage:
    python scripts/run_brief.py --desk defense [--date 2026-06-06]

Requirements:
    - OPENROUTER_API_KEY and OPENAI_API_KEY set in .env
    - Local Supabase running (supabase start)
    - normalized_records populated (run seed_fixtures.py first)
"""
import argparse
import asyncio
import sys
from datetime import date

sys.path.insert(0, "engine")

from engine.brief.analysis import ground_brief_analysis
from engine.brief.generator import persist_brief
from engine.brief.publish import generate_publishable_brief
from engine.db import create_pool
from engine.eval.citation_eval import CitationEvaluator
from engine.settings import settings


async def main(desk: str, brief_date: str) -> int:
    """Generate one desk's brief. Returns an exit code the daily workflow reads (D076):
    0 = published, 3 = generated but failed the publish gate (a clean 'thin desk' skip,
    not an error), 1 = hard failure (provider outage / crash after retries). The
    distinction lets the scheduled run report 'published X, skipped Y' and only alarm on
    a genuine break instead of crying 'all jobs failed' when one sparse desk skips."""
    pool = await create_pool()   # hardened: retries transient DNS/connection failures (D057)

    print(f"Generating {desk.upper()} brief for {brief_date}...")

    evaluator = CitationEvaluator()
    try:
        # Regenerate-on-failure (D072): the synthesis model is non-deterministic, so
        # a failed gate is often a bad draw a re-run clears. Returns the first passing
        # attempt, else the best one seen.
        attempt = await generate_publishable_brief(desk=desk, pool=pool, evaluator=evaluator)
    except RuntimeError as e:
        # Every attempt raised even after call-layer backoff (D076) — a real outage
        # (provider down, key invalid), not a thin-data skip. Surface as a hard failure.
        print(f"Generation failed: {e}")
        await pool.close()
        return 1

    brief = attempt.brief
    item_results = attempt.item_results
    excluded_ids = attempt.excluded_ids
    provable_claims = attempt.provable_claims
    eval_passed = attempt.eval_passed

    print(f"Generated {len(brief.items)} items. Eval results:")
    for i, (item, result) in enumerate(zip(brief.items, item_results)):
        if result.excluded:
            print(f"  [{i+1}] EXCLUDED: {item.get('headline', '')[:60]}")
        else:
            trimmed = "" if result.faithfulness_score == 1.0 else " (trimmed)"
            print(f"  [{i+1}] score={result.faithfulness_score:.2f}{trimmed}: {item.get('headline', '')[:60]}")

    surviving = len(item_results) - len(excluded_ids)
    # Faithfulness is guaranteed by construction — only LLM-supported sentences are
    # published (D069). Publication gates on provable *claims*, not items, because
    # synthesis non-deterministically packs the same facts into few dense items or
    # many thin ones; claim count is stable to that, item count is not (D070).
    score = 1.0 if surviving else 0.0

    pre_clean = evaluator.brief_faithfulness_score(item_results)
    print(f"\nPublished faithfulness: {score:.3f} | pre-clean synthesis: {pre_clean:.3f}")
    print(f"Items: {len(item_results)} generated, {len(excluded_ids)} excluded, {surviving} surviving")
    print(f"Provable claims: {provable_claims}")
    print(f"Eval: {'PASSED' if eval_passed else 'FAILED'} (need >= {settings.brief_min_claims} provable claims)")

    # ── Layered brief (D071 prototype): facts are gated above; the read/watch/
    # convergence layer is ANALYSIS, held only to grounding — it must add no new
    # concrete fact vs the published facts. Print it with grounding flags so we can
    # judge the analysis quality before persisting/rendering it (P2/P3).
    surviving_items = [it for it in brief.items if it.get("_item_id") not in excluded_ids]
    # Ground analysis against the RICH fact set — item headlines + bodies + the source
    # passage excerpts — not just the trimmed body, so a subject the citation gate
    # stripped from the body (e.g. the awardee/amount) is still present for grounding.
    facts_text = "\n".join(
        part
        for part in (
            [it.get("headline", "") for it in surviving_items]
            + [it.get("body", "") for it in surviving_items]
            + [p.excerpt for p in brief.passages]
        )
        if part
    )

    # Grounding gate (D073): regenerate-then-omit any analysis field that fabricates a
    # specific, so only grounded analysis is persisted/rendered. Mutates brief in place.
    report = await ground_brief_analysis(brief, surviving_items, facts_text, evaluator)
    status_by_label = {r.label: r for r in report}

    def _show(label: str, text: str, key: str) -> None:
        text = (text or "").strip()
        res = status_by_label.get(key)
        tag = f" [{res.status}]" if res and res.status in ("regenerated", "omitted") else ""
        if res and res.status == "omitted":
            print(f"  {label}: (omitted — fabricated: {res.fabrications})")
        elif text:
            print(f"  {label}{tag}: {text}")

    print("\n--- LAYERED BRIEF (D071/D073) ---")
    _show("CONVERGENCE", brief.convergence_read, "convergence_read")
    for i, item in enumerate(surviving_items):
        print(f"\n[{i+1}] {item.get('headline', '')}")
        print(f"  FACT: {item.get('body', '')}")
        _show("READ", item.get("read", ""), f"item{i}.read")
        _show("WATCH", item.get("watch", ""), f"item{i}.watch")

    brief_id = await persist_brief(
        brief=brief,
        desk=desk,
        brief_date=brief_date,
        faithfulness_score=score,
        eval_passed=eval_passed,
        excluded_item_ids=excluded_ids,
        pool=pool,
    )
    print(f"\nBrief persisted: {brief_id} (status={'published' if eval_passed else 'failed'})")

    # Print EVAL_BASELINE.md row
    print("\n--- EVAL_BASELINE.md row ---")
    claims_total = sum(r.claims_total for r in item_results if not r.excluded)
    claims_passing = sum(r.claims_passing for r in item_results if not r.excluded)
    print(
        f"| {brief_date} | {desk} | {len(item_results)} | {len(excluded_ids)} "
        f"| {claims_total} | {claims_passing} | {score:.3f} "
        f"| {'Yes' if eval_passed else 'No'} | First integration run |"
    )

    await pool.close()
    # 0 = published, 3 = generated but below the provable-claim floor (a clean skip).
    return 0 if eval_passed else 3


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--desk", default="defense")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.desk, args.date)))
