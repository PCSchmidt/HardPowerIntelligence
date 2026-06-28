"""SAM.gov contract-opportunities adapter (D105) — Phase 2 structured federal veins.

USAspending shows awards *after the fact*; SAM.gov shows the **opportunities** — the
solicitations and pre-solicitations agencies post *before* an award, the earliest
public signal of where federal money is about to flow. A forward-looking, confirmed-tier
primary record for the Defense desk (and cross-desk: AI compute, energy infrastructure
procurements appear here too).

Backed by the keyless-but-keyed SAM.gov Opportunities v2 API (free; requires a
``SAM_GOV_API_KEY`` registered at api.sam.gov — set as a secret before the first ingest;
without it the call 403s and the run is recorded failed, never silent). Shape mirrors the
other probe adapters (NRC/EDGAR/USAspending, D059/D095): each probe is one on-thesis
keyword query tagged to its single home desk (D097); the runner's ``page`` counter walks
the probes. A fixed rolling lookback (not a forward watermark — the trap that zeroed
USAspending, Phase B) + content-hash dedup.
"""
import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from engine.settings import settings

from .base import NormalizedRecord

_SOURCE_ID = "sam_gov"
_BASE_URL = "https://api.sam.gov/opportunities/v2/search"
_LOOKBACK_DAYS = 30        # SAM allows up to a 1-year postedFrom..postedTo range
_LIMIT = 25                # opportunities per probe (most-recent-first)
_TITLE_CHARS = 300


@dataclass(frozen=True)
class _Probe:
    q: str                   # SAM.gov full-text keyword query
    desk: str                # single home desk (D097 demarcation)


# Curated on-thesis procurement keywords — one home desk each. Disjoint enough that a
# notice's desk is deterministic under content-hash dedup; extend freely.
_PROBES: tuple[_Probe, ...] = (
    # Defense
    _Probe("hypersonic", "defense"),
    _Probe("counter-unmanned aircraft", "defense"),
    _Probe("directed energy weapon", "defense"),
    _Probe("unmanned underwater vehicle", "defense"),
    _Probe("munitions production", "defense"),
    _Probe("missile defense", "defense"),
    # AI / compute
    _Probe("artificial intelligence", "ai"),
    _Probe("high performance computing", "ai"),
    _Probe("semiconductor", "ai"),
    # Energy
    _Probe("small modular reactor", "energy"),
    _Probe("microgrid", "energy"),
    _Probe("energy storage", "energy"),
)


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


def _mmddyyyy(d: date) -> str:
    return d.strftime("%m/%d/%Y")


class SAMGovAdapter:
    source_id: str = _SOURCE_ID
    base_url: str = _BASE_URL
    http_method: str = "GET"
    response_format: str = "json"

    def __init__(self) -> None:
        self._active_probe: _Probe = _PROBES[0]

    @property
    def max_pages(self) -> int:
        return len(_PROBES)

    @property
    def probe_count(self) -> int:
        return len(_PROBES)

    # ── parse ────────────────────────────────────────────────────────────────────

    def parse(self, response: dict) -> list[NormalizedRecord]:
        desk = self._active_probe.desk
        q = self._active_probe.q
        records: list[NormalizedRecord] = []

        for row in (response or {}).get("opportunitiesData", []):
            notice_id = _clean(row.get("noticeId"))
            title = _clean(row.get("title"))[:_TITLE_CHARS]
            if not notice_id or not title:
                continue

            agency = _clean(row.get("fullParentPathName"))
            ntype = _clean(row.get("type"))            # Solicitation | Presolicitation | …
            posted = _clean(row.get("postedDate"))
            sol = _clean(row.get("solicitationNumber"))
            link = _clean(row.get("uiLink"))
            naics = _clean(row.get("naicsCode"))

            structured = {
                "notice_id": notice_id,
                "title": title,
                "agency": agency,
                "notice_type": ntype,
                "posted_date": posted,
                "solicitation_number": sol,
                "naics": naics,
                "ui_link": link,
                "query": q,        # probe context; excluded from the hash
            }
            # Hash intrinsic notice fields only (not the probe query) so the same notice
            # surfaced by two probes dedups to one row.
            content_hash = hashlib.sha256(
                f"{notice_id}\n{title}\n{posted}".encode()
            ).hexdigest()

            records.append(NormalizedRecord(
                source_id=_SOURCE_ID,
                record_type="award",            # a procurement opportunity (pre-award)
                desk=[desk],
                entity_mentions=[],             # solicitor is an agency; awardee unknown pre-award
                structured_data=structured,
                text_chunk=self._build_text_chunk(agency, ntype, posted, title),
                content_hash=content_hash,
                native_id=notice_id,
                url=link or f"https://sam.gov/opp/{notice_id}/view",
                fetched_at=datetime.now(timezone.utc),
            ))
        return records

    @staticmethod
    def _build_text_chunk(agency, ntype, posted, title) -> str:
        who = agency or "A federal agency"
        kind = ntype or "opportunity"
        when = f" ({posted})" if posted else ""
        return f'{who} posted a {kind}{when}: "{title}".'

    # ── cursor / request building ──────────────────────────────────────────────────

    def build_request_payload(self, cursor: dict | None, page: int = 1) -> dict:
        probe = _PROBES[(page - 1) % len(_PROBES)]
        self._active_probe = probe
        today = date.today()
        return {
            "api_key": settings.sam_gov_api_key,
            "q": probe.q,
            "postedFrom": _mmddyyyy(today - timedelta(days=_LOOKBACK_DAYS)),
            "postedTo": _mmddyyyy(today),
            "limit": _LIMIT,
        }

    def next_cursor(self, response, current_page: int) -> dict:
        if current_page < len(_PROBES):
            return {"page": current_page + 1}
        return {"last_date": date.today().isoformat()}
