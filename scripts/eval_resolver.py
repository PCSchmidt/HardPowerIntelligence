"""Resolver accuracy gate (T3.2, D091) — operator-run against the seeded DB.

The non-negotiable from the /critical-thinker pass: resolved entities must not render until the
resolver clears an accuracy bar, because a wrong ticker corrupts the provenance trust model. This
resolves each golden mention, maps the resolved entity back to its ticker, compares to the expected
ticker, and FAILS (exit 1) if precision < ``entity_resolver_min_precision``.

Run after seeding (``scripts/seed_entities.py``):

    uv run python scripts/eval_resolver.py
"""
import asyncio
import json
import sys
from pathlib import Path

from engine.db import create_pool
from engine.entity.eval import evaluate
from engine.entity.resolution import find_candidates, resolve_mention
from engine.entity.resolver import normalize_mention
from engine.settings import settings

_GOLDEN = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "entity_golden.json"


async def _ticker_for(conn, entity_id: str | None) -> str | None:
    if entity_id is None:
        return None
    row = await conn.fetchrow(
        "SELECT id_value FROM entity_identifiers "
        "WHERE entity_id = $1::uuid AND id_type = 'ticker' AND valid_to IS NULL LIMIT 1",
        entity_id,
    )
    return row["id_value"] if row else None


async def main() -> int:
    golden = json.loads(_GOLDEN.read_text())
    pool = await create_pool()
    predictions: dict[str, str | None] = {}
    diagnostics: dict[str, str] = {}
    try:
        async with pool.acquire() as conn:
            for mention, expected in golden.items():
                result = await resolve_mention(conn, mention)
                got = await _ticker_for(conn, result.entity_id)
                predictions[mention] = got
                if got != expected:
                    cands = await find_candidates(conn, normalize_mention(mention))
                    top = ", ".join(
                        f"{c.canonical_name!r}~{c.similarity:.2f}" for c in cands[:3]
                    ) or "(no candidates)"
                    diagnostics[mention] = (
                        f"status={result.status.value} conf={result.confidence:.2f} "
                        f"norm={normalize_mention(mention)!r} | top: {top}"
                    )
    finally:
        await pool.close()

    metrics = evaluate(predictions, golden)
    print(metrics.summary())
    for mention, expected in golden.items():
        got = predictions.get(mention)
        print(f"  {'ok' if got == expected else 'XX'} {mention!r}: expected={expected} got={got}")
        if mention in diagnostics:
            print(f"       └ {diagnostics[mention]}")

    # A resolver that links nothing has vacuous precision 1.0 — don't let that read as a pass
    # (usually means the reference set isn't seeded, or matching is broken).
    if metrics.resolvable > 0 and metrics.resolved == 0:
        print("FAIL: resolver linked nothing — is the reference set seeded? (run scripts/seed_entities.py)")
        return 1

    threshold = settings.entity_resolver_min_precision
    if metrics.precision < threshold:
        print(f"FAIL: precision {metrics.precision:.3f} < {threshold} (resolver not trustworthy yet)")
        return 1
    print(f"PASS: precision {metrics.precision:.3f} >= {threshold} (recall {metrics.recall:.3f})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
