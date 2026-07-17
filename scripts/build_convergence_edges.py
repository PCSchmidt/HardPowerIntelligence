"""Recompute the convergence graph's CONVERGES_WITH edges from the published brief layer (§1).

Graph-wide + idempotent: reads every published brief item's linked entities, computes recency-decayed
cross-desk co-appearance edges, and upserts them (retiring any that decayed below the prune floor).
Runs as a post-brief step in the daily cadence — the graph is designed to compound with time as briefs
accrue, so recomputing after each day's briefs land is the whole point.

Best-effort by design: these edges are DERIVED and decorative — the briefs they summarize are already
published and citable. A failure here must never affect the run, so this prints and **exits 0** even on
error (the workflow step is non-gating).

Usage:
    python scripts/build_convergence_edges.py
"""
import asyncio
import sys

sys.path.insert(0, "engine")

from engine.db import create_pool
from engine.entity.graph_builder import build_convergence_edges
from engine.settings import settings


async def main() -> int:
    pool = await create_pool()
    try:
        async with pool.acquire() as conn:
            result = await build_convergence_edges(
                conn,
                half_life_days=settings.convergence_half_life_days,
                weight_floor=settings.convergence_weight_floor,
                cross_desk_boost=settings.convergence_cross_desk_boost,
            )
        print(
            f"convergence edges: {result['upserted']} live "
            f"({result['cross_desk']} cross-desk), {result['retired']} retired, "
            f"from {result['observations']} co-appearances"
        )
    finally:
        await pool.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as exc:  # noqa: BLE001 — derived/decorative; never fail the run over the graph
        print(f"convergence edge build failed (non-fatal): {exc}")
        sys.exit(0)
