"""Inspect the entities linked onto the latest brief (T3.3/T3.4 verification, D091/D092).

Read-only. After a brief runs with the entity linker, this shows exactly what got linked to each
item — the name, ticker, and whether it was minted (private/venture) — plus a summary of entities
minted from brief resolution. Use it to confirm the linker resolves real mentions correctly and that
minting isn't polluting the graph, BEFORE entity chips render in the reader.

    uv run python scripts/inspect_brief_entities.py            # defense (default)
    uv run python scripts/inspect_brief_entities.py energy
"""
import asyncio
import sys

from engine.db import create_pool

_DESK = sys.argv[1] if len(sys.argv) > 1 else "defense"


async def main() -> int:
    pool = await create_pool()
    try:
        async with pool.acquire() as conn:
            brief = await conn.fetchrow(
                "SELECT id::text AS id, date FROM briefs "
                "WHERE desk = $1 AND status = 'published' ORDER BY date DESC, created_at DESC LIMIT 1",
                _DESK,
            )
            if brief is None:
                print(f"No published brief for desk={_DESK}")
                return 1
            print(f"Latest {_DESK} brief {brief['date']} ({brief['id']})\n")

            items = await conn.fetch(
                "SELECT item_type, headline, entity_ids FROM brief_items "
                "WHERE brief_id = $1::uuid ORDER BY display_order",
                brief["id"],
            )
            for it in items:
                ids = list(it["entity_ids"] or [])
                print(f"[{it['item_type']}] {it['headline'][:70]}")
                if not ids:
                    print("      └ (no linked entities)")
                rows = await conn.fetch(
                    """
                    SELECT e.canonical_name AS name,
                           (SELECT id_value FROM entity_identifiers
                            WHERE entity_id = e.id AND id_type = 'ticker' AND valid_to IS NULL LIMIT 1) AS ticker,
                           EXISTS (SELECT 1 FROM entity_identifiers
                                   WHERE entity_id = e.id AND source = 'brief_resolution') AS minted
                    FROM entities e WHERE e.id = ANY($1::uuid[])
                    """,
                    ids,
                )
                for r in rows:
                    tag = r["ticker"] or ("private/minted" if r["minted"] else "no-ticker")
                    print(f"      └ {r['name']}  [{tag}]")
                print()

            minted = await conn.fetch(
                "SELECT DISTINCT e.canonical_name AS name FROM entities e "
                "JOIN entity_identifiers i ON i.entity_id = e.id "
                "WHERE i.source = 'brief_resolution' ORDER BY e.canonical_name"
            )
            print(f"--- Minted from brief resolution: {len(minted)} entities ---")
            for r in minted[:40]:
                print(f"  • {r['name']}")
            if len(minted) > 40:
                print(f"  … and {len(minted) - 40} more")
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
