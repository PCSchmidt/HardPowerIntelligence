import hashlib
import json
from datetime import date, datetime, timezone, timedelta

from .base import NormalizedRecord

_SOURCE_ID = "usaspending"
_BASE_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
_AWARD_TYPE_CODES = ["A", "B", "C", "D"]  # procurement contracts only
_DEFAULT_LOOKBACK_DAYS = 3
_FIELDS = [
    "Award ID", "Recipient Name", "Recipient UEI", "Start Date", "End Date",
    "Award Amount", "Awarding Agency", "Awarding Sub Agency",
    "Contract Award Type", "Place of Performance City Code",
    "Place of Performance State Code", "Last Modified Date",
    "base_and_exercised_options_value", "Award Description", "def_codes",
]


def _sha256(data: dict) -> str:
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _normalize_name(name: str) -> str:
    suffixes = {" INC", " CORP", " LLC", " LTD", " LP", " CO", " CORPORATION",
                " INCORPORATED", " LIMITED", " COMPANY"}
    upper = name.upper().strip()
    for s in suffixes:
        if upper.endswith(s):
            upper = upper[: -len(s)].strip()
    return upper


def _build_text_chunk(row: dict) -> str:
    parts = [
        f"Contract award: {row.get('Award Description', '')}",
        f"Recipient: {row.get('Recipient Name', '')}",
        f"Amount: ${row.get('Award Amount', 0):,.0f}",
        f"Agency: {row.get('Awarding Agency', '')} / {row.get('Awarding Sub Agency', '')}",
        f"Period: {row.get('Start Date', '')} to {row.get('End Date', '')}",
        f"Location: {row.get('Place of Performance City Code', '')}, "
        f"{row.get('Place of Performance State Code', '')}",
    ]
    return " | ".join(p for p in parts if p.split(": ", 1)[-1].strip())


class USASpendingAdapter:
    source_id: str = _SOURCE_ID

    # ── parse ──────────────────────────────────────────────────────────────────

    def parse(self, response: dict) -> list[NormalizedRecord]:
        records = []
        for row in response.get("results", []):
            award_id = row.get("Award ID", "")
            if not award_id:
                continue

            structured = {
                "award_id": award_id,
                "recipient_name": row.get("Recipient Name"),
                "recipient_uei": row.get("Recipient UEI"),
                "amount_usd": row.get("Award Amount"),
                "awarding_agency": row.get("Awarding Agency"),
                "awarding_sub_agency": row.get("Awarding Sub Agency"),
                "contract_type": row.get("Contract Award Type"),
                "description": row.get("Award Description"),
                "start_date": row.get("Start Date"),
                "end_date": row.get("End Date"),
                "last_modified": row.get("Last Modified Date"),
                "place_city": row.get("Place of Performance City Code"),
                "place_state": row.get("Place of Performance State Code"),
            }

            entity_mentions = []
            recipient = row.get("Recipient Name")
            if recipient:
                entity_mentions.append({
                    "mention": recipient,
                    "normalized": _normalize_name(recipient),
                    "entity_id": None,
                    "confidence": None,
                    "resolved_by": None,
                })

            records.append(NormalizedRecord(
                source_id=_SOURCE_ID,
                record_type="contract_award",
                desk=["defense"],
                entity_mentions=entity_mentions,
                structured_data=structured,
                text_chunk=_build_text_chunk(row),
                content_hash=_sha256(structured),
                native_id=award_id,
                url=f"https://www.usaspending.gov/award/{award_id}/",
                fetched_at=datetime.now(timezone.utc),
            ))
        return records

    # ── cursor / request building ──────────────────────────────────────────────

    def build_request_payload(self, cursor: dict | None, page: int = 1) -> dict:
        if cursor and "last_date" in cursor:
            start_date = cursor["last_date"]
        else:
            lookback = date.today() - timedelta(days=_DEFAULT_LOOKBACK_DAYS)
            start_date = lookback.isoformat()

        end_date = date.today().isoformat()

        return {
            "filters": {
                "time_period": [{"start_date": start_date, "end_date": end_date}],
                "award_type_codes": _AWARD_TYPE_CODES,
            },
            "fields": _FIELDS,
            "page": page,
            "limit": 100,
            "sort": "Award Amount",
            "order": "desc",
        }

    def next_cursor(self, response: dict, current_page: int) -> dict:
        meta = response.get("page_metadata", {})
        if meta.get("has_next_page"):
            return {"page": current_page + 1}
        return {"last_date": date.today().isoformat()}
