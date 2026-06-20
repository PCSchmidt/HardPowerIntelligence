"""Brief-quality report (Phase 1 measurement) — read-only, operator-run.

Turns "are the desks good?" into a repeatable measurement instead of eyeballing one run. For the
last N days of published briefs it reports, per desk per day: item count, faithfulness, item-type
mix, source mix (which adapters actually fed the brief), and entity coverage — plus a window-level
source tally and any cross-desk repeats (the same source record surfacing on >1 desk the same day).

Use it to watch the curation/source changes soak before deciding the next steps:

    uv run python scripts/brief_quality_report.py        # last 7 days
    uv run python scripts/brief_quality_report.py 14
"""
import asyncio
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta

from engine.db import create_pool

_DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 7


async def main() -> int:
    since = date.today() - timedelta(days=_DAYS)
    pool = await create_pool()
    try:
        async with pool.acquire() as conn:
            briefs = await conn.fetch(
                "SELECT id::text AS id, desk, date, faithfulness_score "
                "FROM briefs WHERE date >= $1 AND status = 'published' "
                "ORDER BY date DESC, desk",
                since,
            )
            if not briefs:
                print(f"No published briefs in the last {_DAYS} days.")
                return 0
            ids = [b["id"] for b in briefs]
            items = await conn.fetch(
                "SELECT brief_id::text AS brief_id, item_type, "
                "       coalesce(array_length(entity_ids, 1), 0) AS n_entities "
                "FROM brief_items WHERE brief_id = ANY($1::uuid[])",
                ids,
            )
            cites = await conn.fetch(
                "SELECT brief_id::text AS brief_id, source_id, native_id "
                "FROM citations WHERE brief_id = ANY($1::uuid[])",
                ids,
            )

        items_by_brief: dict[str, list] = defaultdict(list)
        for it in items:
            items_by_brief[it["brief_id"]].append(it)
        cites_by_brief: dict[str, list] = defaultdict(list)
        for c in cites:
            cites_by_brief[c["brief_id"]].append(c)

        window_sources: Counter = Counter()
        # (date, source_id, native_id) -> set of desks, for cross-desk repeat detection
        record_desks: dict[tuple, set] = defaultdict(set)
        brief_desk = {b["id"]: (b["desk"], b["date"]) for b in briefs}

        print(f"Brief-quality report — last {_DAYS} days (since {since})\n")
        for b in briefs:
            its = items_by_brief.get(b["id"], [])
            cs = cites_by_brief.get(b["id"], [])
            types = Counter(it["item_type"] for it in its)
            srcs = Counter(c["source_id"] for c in cs)
            window_sources.update(srcs)
            with_entities = sum(1 for it in its if it["n_entities"] > 0)
            for c in cs:
                record_desks[(b["date"], c["source_id"], c["native_id"])].add(b["desk"])
            faith = b["faithfulness_score"]
            faith_s = f"{faith:.2f}" if faith is not None else "  - "
            types_s = " ".join(f"{k}×{v}" for k, v in types.most_common())
            srcs_s = " ".join(f"{k}×{v}" for k, v in srcs.most_common()) or "(none)"
            print(f"{b['date']}  {b['desk']:8} | {len(its):2} items | faith {faith_s} | "
                  f"entities {with_entities}/{len(its)} | types: {types_s} | sources: {srcs_s}")

        print("\n--- window source tally (citations) ---")
        for src, n in window_sources.most_common():
            print(f"  {src:14} {n}")

        repeats = {k: v for k, v in record_desks.items() if len(v) > 1}
        print(f"\n--- cross-desk repeats (same record on >1 desk, same day): {len(repeats)} ---")
        for (d, src, nid), desks in sorted(repeats.items())[:25]:
            print(f"  {d} {src}:{nid} → {sorted(desks)}")
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
