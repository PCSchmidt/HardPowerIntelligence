"""Backfill name-gazetteer entity links onto already-published brief items (§4 coverage lift).

The gazetteer (`engine.entity.gazetteer`) links future briefs automatically at generation time, but
historical briefs were persisted before it existed and are never regenerated — so their `entity_ids`
stay identifier-only (news/feeds unlinked). This one-time (re-runnable) pass unions each published
item's existing links with the multi-word names found in its headline+body, and updates the row when
that adds anything. Idempotent: the union is deterministic from the text, so re-running is a no-op.

Enrichment only — it never removes an existing link and never touches item text; the visible effect is
additional (correct) entity chips + a denser convergence graph. Re-run `build_convergence_edges.py`
after this to recompute edges over the enriched links.

    python scripts/backfill_item_entities.py [--dry-run]
"""
import argparse
import asyncio
import sys

sys.path.insert(0, "engine")

from engine.db import create_pool
from engine.entity.gazetteer import find_mentions, load_alias_index


async def main(dry_run: bool) -> int:
    pool = await create_pool()
    try:
        async with pool.acquire() as conn:
            index = await load_alias_index(conn)
            items = await conn.fetch(
                "SELECT bi.id, bi.headline, bi.body, bi.entity_ids "
                "FROM brief_items bi JOIN briefs b ON b.id = bi.brief_id WHERE b.status = 'published'"
            )
            updated = 0
            links_added = 0
            for it in items:
                current = [str(x) for x in (it["entity_ids"] or [])]
                seen = set(current)
                additions = [g for g in find_mentions(f"{it['headline']} {it['body']}", index)
                             if g not in seen]
                if not additions:
                    continue
                updated += 1
                links_added += len(additions)
                if not dry_run:
                    await conn.execute(
                        "UPDATE brief_items SET entity_ids = $2::uuid[] WHERE id = $1",
                        it["id"], current + additions,
                    )
            verb = "would update" if dry_run else "updated"
            print(f"{verb} {updated} items (+{links_added} entity links) over {len(items)} published items")
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.dry_run)))
