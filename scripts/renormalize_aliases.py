"""Backfill entity_aliases.alias_normalized after a normalize_mention change (T3.2, D091).

Operator-run (writes to the cloud DB). The seed (scripts/seed_entities.py) is
insert-if-not-exists keyed on ticker, so a change to ``normalize_mention`` does NOT
retroactively fix aliases already stored — the stale normalized form keeps tanking trigram
recall (this is the Northrop Grumman "/DE/" miss). This recomputes ``alias_normalized`` from
the original ``alias`` for every row where it has drifted, in small batches.

Idempotent: a second run after no normalize_mention change updates nothing. Run after editing
``normalize_mention``, before ``scripts/eval_resolver.py``:

    uv run python scripts/renormalize_aliases.py
"""
import asyncio
import sys

from engine.db import create_pool
from engine.entity.resolver import normalize_mention

_BATCH = 500


async def main() -> int:
    pool = await create_pool()
    updated = 0
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id::text AS id, alias, alias_normalized FROM entity_aliases"
            )
        # Recompute in Python (normalize_mention's suffix logic isn't expressible in pure SQL);
        # only touch rows whose normalized form actually changed.
        stale = [
            (r["id"], normalize_mention(r["alias"]))
            for r in rows
            if r["alias"] and normalize_mention(r["alias"]) != r["alias_normalized"]
        ]
        print(f"Scanned {len(rows)} aliases | stale: {len(stale)}")

        for start in range(0, len(stale), _BATCH):
            batch = stale[start : start + _BATCH]
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.executemany(
                        "UPDATE entity_aliases SET alias_normalized = $2 WHERE id = $1::uuid",
                        batch,
                    )
            updated += len(batch)
            print(f"  progress: {updated}/{len(stale)}")

        print(f"Done: updated={updated}, unchanged={len(rows) - updated}")
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
