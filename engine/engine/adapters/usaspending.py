"""USASpending.gov awards adapter — federal contract & grant awards (the federal-money leg)."""
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .base import NormalizedRecord

_SOURCE_ID = "usaspending"
_BASE_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
# USAspending filters by award ACTION date, but an award appears in the API weeks after that
# date (reporting lag). So we always query a FIXED ROLLING LOOKBACK (not a forward watermark that
# would shrink to ~1 day and return nothing) wide enough to cover the lag; content-hash dedup
# (D057) drops the repeats. 45 days balances catching lagged awards against page volume.
_LOOKBACK_DAYS = 45

# An award whose period of performance STARTED years ago is a pre-existing/parent award
# resurfacing on a recent administrative modification — not "material today." spending_by_award
# returns these (a 1993-dated $22B Boeing/NASA ceiling appeared in the 7/5 Defense wire) because a
# recent mod lands in the action-date window while Start Date stays decades back. Drop awards whose
# start date predates this horizon — a coarse recency floor, generous (4y) so normal multi-year
# awards stay while legacy ceilings are cut (D123).
_MAX_AWARD_AGE_DAYS = 4 * 365

# award_type_codes are segregated by group in spending_by_award (you cannot mix contract
# and assistance types in one query). Defense capital is procurement *contracts* (A–D);
# AI/Energy capital formation (DOE/NSF/ARPA-E research + buildout) flows as *grants /
# financial assistance* (02–05) — confirmed against the live API: contract-only AI queries
# returned generic gov-IT noise, while the real AI/energy money is in grants. So each probe
# carries its own award-type group (D063).
_CONTRACTS = ("A", "B", "C", "D")
_GRANTS = ("02", "03", "04", "05")  # block / formula / project grants + cooperative agreements

# Fields valid for BOTH award groups (verified live) — no contract-only fields, so one
# request shape serves contracts and grants alike; parse() tolerates missing keys.
_FIELDS = [
    "Award ID", "Recipient Name", "Recipient UEI", "Award Amount",
    "Awarding Agency", "Awarding Sub Agency", "Start Date", "End Date",
    "Last Modified Date", "Award Description",
]


@dataclass(frozen=True)
class _Probe:
    keywords: tuple[str, ...]
    desks: tuple[str, ...]
    award_types: tuple[str, ...]


# Cross-desk thematic probes (D059 generalized across desks, D063). USAspending is no
# longer pigeonholed to Defense: it's a feed of *government capital formation* across all
# three desks. Its keyword search indexes PSC/NAICS code *descriptions*, so PSC-informed
# terms act as a cross-agency category filter. Each probe is one API query (keywords
# OR-combined) with its own award-type group; probes are walked via the runner's page
# counter. Keyword sets are DISJOINT so a record's desk tag is deterministic under
# content-hash dedup. Multi-desk probes (space, autonomy, rare earth) are the convergence signal.
_PROBES: tuple[_Probe, ...] = (
    # Space → Defense ∩ AI (procurement contracts). Civil/military space is both a
    # defense capability (ISR, launch, comms) AND AI infrastructure — space-based
    # data centers and satellite-internet connectivity — so space awards (incl. NASA
    # civil-space) are tagged to both desks rather than excluded (D065, per operator).
    _Probe((
        "satellite", "spacecraft", "launch vehicle", "space launch", "geospatial",
        "satellite communications", "space-based",
    ), ("defense", "ai"), _CONTRACTS),
    # Kinetic & sensing defense → Defense (procurement contracts)
    _Probe((
        "directed energy", "high energy laser", "laser weapon", "microwave weapon",
        "unmanned aircraft", "unmanned aerial", "drone", "loitering munition",
        "guided missile", "hypersonic", "precision strike", "munition", "warhead",
        "radar", "surveillance", "reconnaissance", "electro-optical", "infrared sensor",
        "night vision", "signals intelligence", "electronic warfare", "electronic attack",
    ), ("defense",), _CONTRACTS),
    # Autonomy / AI-for-defense → Defense ∩ AI (procurement contracts — drones, robotics)
    _Probe((
        "autonomous", "autonomy", "robotic", "robotics", "counter-uas",
        "artificial intelligence", "machine learning", "command and control",
    ), ("defense", "ai"), _CONTRACTS),
    # AI compute build-out → AI (DOE/NSF/ARPA-E grants — research + infrastructure)
    _Probe((
        "data center", "high performance computing", "supercomputer", "semiconductor",
        "advanced computing", "quantum computing", "exascale",
    ), ("ai",), _GRANTS),
    # Energy transformation → Energy (DOE/ARPA-E grants)
    _Probe((
        "small modular reactor", "grid modernization", "transmission line",
        "energy storage", "grid scale battery", "nuclear power", "hydrogen",
        "geothermal", "carbon capture", "high-assay low-enriched uranium",
    ), ("energy",), _GRANTS),
    # Trilateral chokepoint → Energy ∩ Defense ∩ AI (DOE/critical-minerals grants).
    # Energy-HOME (desk[0]) on purpose: these are DOE/ARPA-E mineral-processing grants
    # whose native home is the Energy desk; left defense-home, every small grant routed
    # onto Defense (boosted by the desk_count convergence multiplier) and crowded out the
    # actual defense thesis (operator review, 2026-06-30). The all-three tag is retained
    # as the convergence marker (entity graph + materiality boost); only the home moves.
    _Probe(("rare earth", "critical minerals"), ("energy", "defense", "ai"), _GRANTS),
)


def _sha256(data: dict) -> str:
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _award_too_old(start_date: str | None) -> bool:
    """True if the award's period started before the recency floor (D123).

    Fail-open: a missing/unparseable date keeps the award (never drop on ambiguity)."""
    if not start_date:
        return False
    try:
        start = date.fromisoformat(start_date[:10])
    except ValueError:
        return False
    return start < date.today() - timedelta(days=_MAX_AWARD_AGE_DAYS)


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
        f"Federal award: {row.get('Award Description', '')}",
        f"Recipient: {row.get('Recipient Name', '')}",
        f"Amount: ${row.get('Award Amount', 0):,.0f}",
        f"Agency: {row.get('Awarding Agency', '')} / {row.get('Awarding Sub Agency', '')}",
        f"Period: {row.get('Start Date', '')} to {row.get('End Date', '')}",
    ]
    return " | ".join(p for p in parts if p.split(": ", 1)[-1].strip())


class USASpendingAdapter:
    source_id: str = _SOURCE_ID
    base_url: str = _BASE_URL
    http_method: str = "POST"   # USAspending search is a POST with a JSON body

    def __init__(self) -> None:
        # Set per request in build_request_payload, read in parse() (the runner calls
        # build → fetch → parse sequentially on one instance). Defaults to the first
        # probe so parse() works standalone (e.g. in tests).
        self._active_probe: _Probe = _PROBES[0]

    @property
    def probe_count(self) -> int:
        return len(_PROBES)

    # ── parse ──────────────────────────────────────────────────────────────────

    def parse(self, response: dict) -> list[NormalizedRecord]:
        records = []
        desks = list(self._active_probe.desks)
        for row in response.get("results", []):
            award_id = row.get("Award ID", "")
            if not award_id:
                continue
            if _award_too_old(row.get("Start Date")):
                continue   # legacy/parent ceiling resurfacing on a recent mod — not news (D123)

            structured = {
                "award_id": award_id,
                "recipient_name": row.get("Recipient Name"),
                "recipient_uei": row.get("Recipient UEI"),
                "amount_usd": row.get("Award Amount"),
                "awarding_agency": row.get("Awarding Agency"),
                "awarding_sub_agency": row.get("Awarding Sub Agency"),
                "description": row.get("Award Description"),
                "start_date": row.get("Start Date"),
                "end_date": row.get("End Date"),
                "last_modified": row.get("Last Modified Date"),
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
                record_type="federal_award",
                desk=desks,
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
        # page (1-based) selects the probe; the cursor carries ONLY the probe page, not a date
        # watermark. The window is always a fixed rolling lookback (see _LOOKBACK_DAYS) because
        # USAspending awards lag — a forward-advancing watermark shrank this to ~1 day and the
        # source silently fetched 0 (Phase B finding, 2026-06-19). Dedup absorbs the repeats.
        probe = _PROBES[(page - 1) % len(_PROBES)]
        self._active_probe = probe

        start_date = (date.today() - timedelta(days=_LOOKBACK_DAYS)).isoformat()

        return {
            "filters": {
                "time_period": [{"start_date": start_date, "end_date": date.today().isoformat()}],
                "award_type_codes": list(probe.award_types),
                "keywords": list(probe.keywords),  # cross-desk thematic filter (D059/D063)
            },
            "fields": _FIELDS,
            "page": 1,  # always first page; `page` arg selects the PROBE, not API pagination
            "limit": 100,
            "sort": "Award Amount",
            "order": "desc",
        }

    def next_cursor(self, response: dict, current_page: int) -> dict:
        # Walk every probe once per run, then advance the date watermark.
        if current_page < len(_PROBES):
            return {"page": current_page + 1}
        return {"last_date": date.today().isoformat()}
