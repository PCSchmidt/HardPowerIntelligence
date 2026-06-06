from dataclasses import dataclass
from datetime import datetime, timezone

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
    fetched_at: datetime
    native_id: str
    excerpt: str


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
            "UPDATE normalized_records SET embedding = $2 WHERE id = $1",
            [(str(uid), f"[{','.join(str(x) for x in emb)}]") for uid, emb in updates],
        )

    log.info("embeddings_generated", count=len(rows))
    return len(rows)


async def build_query_vector(
    pool: asyncpg.Pool,
    since: datetime,
    top_k_seed: int = 5,
) -> list[float] | None:
    """Embed the top-K (by recency and payload size) records' text_chunks
    as the RAG query vector. Returns None if no embedded records exist."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT text_chunk FROM normalized_records
            WHERE created_at >= $1
              AND embedding IS NOT NULL
              AND text_chunk IS NOT NULL
            ORDER BY created_at DESC, payload_size_bytes DESC NULLS LAST
            LIMIT $2
            """,
            since,
            top_k_seed,
        )

    if not rows:
        return None

    seed_text = " | ".join(r["text_chunk"] for r in rows)
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
) -> list[PassageContext]:
    """Cosine similarity retrieval of top-K passages since window start."""
    vector_str = f"[{','.join(str(x) for x in query_vector)}]"

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                nr.id            AS nr_id,
                nr.source_id,
                nr.text_chunk    AS excerpt,
                rr.id            AS rr_id,
                rr.url,
                rr.fetched_at,
                rr.native_id
            FROM normalized_records nr
            JOIN raw_records rr ON rr.id = nr.raw_record_id
            WHERE nr.embedding IS NOT NULL
              AND nr.created_at >= $1
            ORDER BY nr.embedding <=> $2::vector
            LIMIT $3
            """,
            since,
            vector_str,
            top_k,
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
        )
        for i, row in enumerate(rows)
    ]
