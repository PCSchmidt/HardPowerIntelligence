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

from engine.brief.generator import generate_brief, persist_brief
from engine.db import create_pool
from engine.eval.citation_eval import CitationEvaluator
from engine.settings import settings


async def main(desk: str, brief_date: str) -> None:
    pool = await create_pool()   # hardened: retries transient DNS/connection failures (D057)

    print(f"Generating {desk.upper()} brief for {brief_date}...")

    try:
        brief = await generate_brief(desk=desk, pool=pool)
    except RuntimeError as e:
        print(f"Generation failed: {e}")
        await pool.close()
        return

    print(f"Generated {len(brief.items)} items. Running eval...")

    evaluator = CitationEvaluator()
    item_results = []
    excluded_ids: set[str] = set()

    for i, item in enumerate(brief.items):
        item_id = f"item-{i}"
        item["_item_id"] = item_id
        result = await evaluator.eval_item(
            item_id=item_id,
            body=item.get("body", ""),
            passages=brief.passages,
        )
        item_results.append(result)
        if result.excluded:
            excluded_ids.add(item_id)
            print(f"  [{i+1}] EXCLUDED: {item.get('headline', '')[:60]}")
        else:
            print(f"  [{i+1}] score={result.faithfulness_score:.2f}: {item.get('headline', '')[:60]}")

    score = evaluator.brief_faithfulness_score(item_results)
    surviving = len(item_results) - len(excluded_ids)
    eval_passed = score >= settings.brief_faithfulness_threshold and surviving >= settings.brief_min_items

    print(f"\nBrief faithfulness score: {score:.3f} (threshold: {settings.brief_faithfulness_threshold})")
    print(f"Items: {len(item_results)} generated, {len(excluded_ids)} excluded, {surviving} surviving")
    print(f"Eval: {'PASSED' if eval_passed else 'FAILED'}")

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--desk", default="defense")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    asyncio.run(main(args.desk, args.date))
