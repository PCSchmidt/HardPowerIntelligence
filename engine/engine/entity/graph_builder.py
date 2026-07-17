"""Convergence-graph edge computation (Convergence-graph §1, 2026-07-16).

Computes ``CONVERGES_WITH`` co-appearance edges from the published brief layer: two entities that keep
turning up together — especially *across desks* — are the cross-sector convergence the product is
about. Derived from ``brief_items.entity_ids`` (the curated, published links), so the graph inherits
the linker's precision-first honesty rather than inventing associations.

Design (the choices that decide whether time compounds *signal* or *noise*):

- **Recency-decayed weight.** Each co-appearance contributes ``0.5 ** (age / half_life)`` — a pairing
  seen once last spring barely registers; seen repeatedly this month it dominates. For an investment
  read, convergence *now* must outweigh stale convergence.
- **Cross-desk emphasis.** A pair whose co-appearances span more than one desk (Defense↔Energy) is the
  convergence signal; a same-desk pairing is ordinary. Cross-desk weight is multiplied by a boost, so
  a genuinely cross-sector pairing clears the floor on thinner evidence than an intra-desk one.
- **Prune floor.** Below a weight floor an edge is coincidence — dropped, not rendered. This is the
  anti-hairball guard: without it the graph grows denser but *less* legible as briefs accrue.

The module is pure (no DB) so the weighting/decay/pruning is unit-testable against hand-computed
fixtures; :mod:`engine.entity.graph_persist`-style wiring lives in the DB layer below (``build_*``).
Edges are UNDIRECTED — stored canonically (``from_id <= to_id`` as text) so a pair is one row.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone


@dataclass(frozen=True)
class CoAppearance:
    """One observation that entities ``a`` and ``b`` appeared together, on ``desk``, on ``at``."""
    a: str
    b: str
    desk: str
    at: date


@dataclass(frozen=True)
class ConvergenceEdge:
    """A computed, un-pruned convergence edge, canonically ordered (``from_id <= to_id``)."""
    from_id: str
    to_id: str
    weight: float
    confidence: float
    co_count: int
    desks: tuple[str, ...]
    cross_desk: bool
    last_seen: date


def canonical_pair(a: str, b: str) -> tuple[str, str]:
    """Order a pair deterministically so an undirected edge is stored once (not A→B and B→A)."""
    return (a, b) if a <= b else (b, a)


def recency_weight(age_days: float, half_life_days: float) -> float:
    """Exponential decay: 1.0 at age 0, 0.5 at one half-life, 0.25 at two. Never negative."""
    if half_life_days <= 0:
        return 1.0
    return 0.5 ** (max(0.0, age_days) / half_life_days)


def confidence_from_weight(weight: float) -> float:
    """Squash an unbounded weight into the edge ``confidence`` column's [0,1] range.

    ``1 - 0.5**weight``: weight 1 → 0.5, 2 → 0.75, 3 → 0.875. Monotonic, asymptotes to 1, so a
    strong-but-finite convergence never quite claims certainty. Always a valid CHECK (0..1) value.
    """
    return 1.0 - 0.5 ** max(0.0, weight)


def pairs_from_item(entity_ids: Sequence[str], desk: str, at: date) -> Iterator[CoAppearance]:
    """Every unordered pair of the distinct entities linked to one brief item, tagged desk+date."""
    uniq = list(dict.fromkeys(entity_ids))  # de-dup, preserve order
    for i in range(len(uniq)):
        for j in range(i + 1, len(uniq)):
            yield CoAppearance(uniq[i], uniq[j], desk, at)


@dataclass
class _Acc:
    raw_weight: float = 0.0
    co_count: int = 0
    desks: set[str] = field(default_factory=set)
    last_seen: date | None = None


def compute_edges(
    observations: Iterable[CoAppearance],
    *,
    now: date,
    half_life_days: float,
    weight_floor: float,
    cross_desk_boost: float,
) -> list[ConvergenceEdge]:
    """Aggregate co-appearance observations into pruned, weighted convergence edges.

    Self-pairs are dropped. Pairs are canonicalized so ``(a,b)`` and ``(b,a)`` aggregate together.
    A pair is kept only if its (cross-desk-boosted) recency-decayed weight clears ``weight_floor``.
    Returned strongest-first (deterministic tiebreak on the id pair).
    """
    agg: dict[tuple[str, str], _Acc] = {}
    for ob in observations:
        if ob.a == ob.b:
            continue
        key = canonical_pair(ob.a, ob.b)
        acc = agg.setdefault(key, _Acc())
        acc.raw_weight += recency_weight((now - ob.at).days, half_life_days)
        acc.co_count += 1
        acc.desks.add(ob.desk)
        if acc.last_seen is None or ob.at > acc.last_seen:
            acc.last_seen = ob.at

    edges: list[ConvergenceEdge] = []
    for (frm, to), acc in agg.items():
        cross = len(acc.desks) > 1
        weight = acc.raw_weight * (cross_desk_boost if cross else 1.0)
        if weight < weight_floor:
            continue
        assert acc.last_seen is not None
        edges.append(ConvergenceEdge(
            from_id=frm,
            to_id=to,
            weight=round(weight, 6),
            confidence=round(confidence_from_weight(weight), 6),
            co_count=acc.co_count,
            desks=tuple(sorted(acc.desks)),
            cross_desk=cross,
            last_seen=acc.last_seen,
        ))
    edges.sort(key=lambda e: (-e.weight, e.from_id, e.to_id))
    return edges


# ── DB layer (best-effort recompute; mirrors the linker's post-transaction pattern) ──────────────

async def fetch_coappearances(conn) -> list[CoAppearance]:
    """Explode every published brief item's linked entities into pairwise co-appearances."""
    rows = await conn.fetch(
        "SELECT bi.entity_ids AS entity_ids, b.desk AS desk, b.date AS at "
        "FROM brief_items bi JOIN briefs b ON b.id = bi.brief_id "
        "WHERE b.status = 'published' AND array_length(bi.entity_ids, 1) >= 2"
    )
    obs: list[CoAppearance] = []
    for r in rows:
        ids = [str(x) for x in (r["entity_ids"] or [])]
        obs.extend(pairs_from_item(ids, r["desk"], r["at"]))
    return obs


async def persist_edges(conn, edges: list[ConvergenceEdge], *, now: datetime) -> dict:
    """Idempotently upsert live CONVERGES_WITH edges and retire those that fell below the floor.

    Upsert keys off the ``entity_edges_live_pair`` partial unique index; ``valid_from`` is preserved
    on conflict (it marks when the convergence FIRST appeared), while weight/confidence/desks refresh.
    Any previously-live edge absent from ``edges`` is soft-closed (``valid_to`` set) so a convergence
    that decayed out of significance stops rendering but keeps its bitemporal history.
    """
    desired: set[tuple[str, str]] = {(e.from_id, e.to_id) for e in edges}
    for e in edges:
        props = json.dumps({
            "weight": e.weight,
            "co_count": e.co_count,
            "desks": list(e.desks),
            "cross_desk": e.cross_desk,
            "last_seen": e.last_seen.isoformat(),
        })
        await conn.execute(
            "INSERT INTO entity_edges "
            "  (from_entity_id, to_entity_id, edge_type, properties, confidence, valid_from) "
            "VALUES ($1::uuid, $2::uuid, 'CONVERGES_WITH', $3::jsonb, $4, $5) "
            "ON CONFLICT (from_entity_id, to_entity_id, edge_type) WHERE valid_to IS NULL "
            "DO UPDATE SET properties = EXCLUDED.properties, "
            "              confidence = EXCLUDED.confidence, "
            "              transaction_time = now()",
            e.from_id, e.to_id, props, e.confidence, now,
        )

    live = await conn.fetch(
        "SELECT from_entity_id::text AS f, to_entity_id::text AS t FROM entity_edges "
        "WHERE edge_type = 'CONVERGES_WITH' AND valid_to IS NULL"
    )
    retired = 0
    for r in live:
        if (r["f"], r["t"]) not in desired:
            await conn.execute(
                "UPDATE entity_edges SET valid_to = $3, transaction_time = now() "
                "WHERE from_entity_id = $1::uuid AND to_entity_id = $2::uuid "
                "AND edge_type = 'CONVERGES_WITH' AND valid_to IS NULL",
                r["f"], r["t"], now,
            )
            retired += 1
    return {"upserted": len(edges), "retired": retired}


async def build_convergence_edges(
    conn,
    *,
    half_life_days: float,
    weight_floor: float,
    cross_desk_boost: float,
) -> dict:
    """End-to-end recompute: fetch published co-appearances → compute → persist. Returns a summary."""
    now = datetime.now(timezone.utc)
    observations = await fetch_coappearances(conn)
    edges = compute_edges(
        observations,
        now=now.date(),
        half_life_days=half_life_days,
        weight_floor=weight_floor,
        cross_desk_boost=cross_desk_boost,
    )
    result = await persist_edges(conn, edges, now=now)
    result["observations"] = len(observations)
    result["cross_desk"] = sum(1 for e in edges if e.cross_desk)
    return result
