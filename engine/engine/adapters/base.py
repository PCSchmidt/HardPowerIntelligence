from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class NormalizedRecord:
    """Output of adapter.parse() — one per logical record extracted from a raw payload."""
    source_id: str
    record_type: str
    desk: list[str]
    entity_mentions: list[dict]   # [{mention, normalized, entity_id, confidence, resolved_by}]
    structured_data: dict
    text_chunk: str
    content_hash: str             # SHA-256 of canonical payload bytes
    native_id: str                # source's own identifier
    raw_record_id: str | None = None  # set after raw_record is persisted
    url: str = ""
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
