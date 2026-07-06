import json
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import asyncpg
import openai
import structlog

from engine.settings import settings

log = structlog.get_logger()


@dataclass(frozen=True)
class PassageContext:
    index: int           # 1-based; this IS the [CITE:N] index
    raw_record_id: str
    source_id: str
    url: str
    fetched_at: datetime               # when WE retrieved it (always ~today for a daily run)
    native_id: str
    excerpt: str
    published_at: datetime | None = None   # when the SOURCE published/acted — for staleness (D129)


# Per-source: which structured_data key holds the item's real publication/action date, in
# preference order. Surfaced to the reader as "Published <date>" so staleness is visible; a
# missing/unparseable date degrades to the fetch date labelled "Retrieved" — the item is never
# dropped for lacking a date (operator directive, D129).
_PUBLISHED_KEYS: dict[str, tuple[str, ...]] = {
    "feeds": ("published",),
    "arxiv": ("published", "updated"),
    "gdelt": ("seendate",),
    "usaspending": ("start_date", "last_modified"),   # the award's own date = an honest staleness cue
    "edgar": ("file_date",),
    "nrc": ("publication_date",),
    "sam_gov": ("posted_date", "published"),
}
# Tried after the source-specific keys, for any source whose shape we don't special-case.
_FALLBACK_KEYS = ("published", "publication_date", "posted_date", "file_date", "date", "start_date", "seendate")
_COMPACT_FORMATS = ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S", "%Y%m%d")   # GDELT-style compact stamps


def _parse_published(value) -> datetime | None:
    """Parse one heterogeneous date value (ISO, RFC-822 RSS, compact GDELT) → aware datetime."""
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:  # ISO: "2026-01-15", "2026-01-15T12:00:00Z"
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:  # RFC-822: RSS pubDate "Mon, 28 Jun 2026 12:00:00 GMT"
        dt = parsedate_to_datetime(s)
        if dt is not None:
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass
    for fmt in _COMPACT_FORMATS:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def extract_published_at(source_id: str, structured_data) -> datetime | None:
    """Best-effort canonical publication/action date for a record; ``None`` if unknown (D129).

    Never raises and never signals "drop me" — an unknown date just means the reader shows the
    retrieval date instead."""
    if isinstance(structured_data, str):
        try:
            structured_data = json.loads(structured_data)
        except (ValueError, TypeError):
            return None
    if not isinstance(structured_data, dict):
        return None
    for key in _PUBLISHED_KEYS.get(source_id, ()) + _FALLBACK_KEYS:
        dt = _parse_published(structured_data.get(key))
        if dt is not None:
            return dt
    return None


async def embed_pending_records(pool: asyncpg.Pool, since: datetime) -> int:
    """Batch-embed any normalized_records in the window with embedding IS NULL.
    Returns number of records embedded.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, text_chunk FROM normalized_records
            WHERE created_at >= $1 AND embedding IS NULL AND text_chunk IS NOT NULL
            """,
            since,
        )

    if not rows:
        return 0

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    texts = [r["text_chunk"] for r in rows]

    response = await client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
        dimensions=settings.embedding_dimensions,
    )

    updates = [
        (rows[i]["id"], response.data[i].embedding)
        for i in range(len(rows))
    ]

    async with pool.acquire() as conn:
        await conn.executemany(
            "UPDATE normalized_records SET embedding = $2::vector WHERE id = $1",
            [(str(uid), f"[{','.join(str(x) for x in emb)}]") for uid, emb in updates],
        )

    log.info("embeddings_generated", count=len(rows))
    return len(rows)


async def build_query_vector(
    pool: asyncpg.Pool,
    since: datetime,
    desk: str,
    top_k_seed: int = 5,
    seed_texts: list[str] | None = None,
) -> list[float] | None:
    """Embed seed text_chunks as the RAG query vector. By default seeds from the
    most *material* desk records, supplied via ``seed_texts`` (D068) — a high-volume
    source must not hijack retrieval by recency. Falls back to the top-K (by recency)
    desk records when ``seed_texts`` is None. ``desk`` membership includes multi-desk
    records (convergence). Returns None if there is nothing to seed from."""
    if seed_texts is not None:
        seeds = [t for t in seed_texts[:top_k_seed] if t]
    else:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT text_chunk FROM normalized_records
                WHERE created_at >= $1
                  AND $2 = ANY(desk)
                  AND embedding IS NOT NULL
                  AND text_chunk IS NOT NULL
                ORDER BY created_at DESC
                LIMIT $3
                """,
                since,
                desk,
                top_k_seed,
            )
        seeds = [r["text_chunk"] for r in rows]

    if not seeds:
        return None

    seed_text = " | ".join(seeds)
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.embeddings.create(
        model=settings.embedding_model,
        input=[seed_text],
        dimensions=settings.embedding_dimensions,
    )
    return response.data[0].embedding


async def fetch_passages(
    pool: asyncpg.Pool,
    query_vector: list[float],
    since: datetime,
    top_k: int,
    desk: str,
) -> list[PassageContext]:
    """Cosine-similarity retrieval of top-K passages for the desk since window
    start. ``desk`` membership includes multi-desk records (convergence)."""
    vector_str = f"[{','.join(str(x) for x in query_vector)}]"

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                nr.id            AS nr_id,
                nr.source_id,
                nr.text_chunk    AS excerpt,
                nr.structured_data,
                rr.id            AS rr_id,
                rr.url,
                rr.fetched_at,
                rr.native_id
            FROM normalized_records nr
            JOIN raw_records rr ON rr.id = nr.raw_record_id
            WHERE nr.embedding IS NOT NULL
              AND nr.created_at >= $1
              AND $4 = ANY(nr.desk)
            ORDER BY nr.embedding <=> $2::vector
            LIMIT $3
            """,
            since,
            vector_str,
            top_k,
            desk,
        )

    return [
        PassageContext(
            index=i + 1,
            raw_record_id=str(row["rr_id"]),
            source_id=row["source_id"],
            url=row["url"],
            fetched_at=row["fetched_at"],
            native_id=row["native_id"],
            excerpt=row["excerpt"] or "",
            published_at=extract_published_at(row["source_id"], row["structured_data"]),
        )
        for i, row in enumerate(rows)
    ]
