"""SEC EDGAR full-text search adapter (D055 §10, D060).

The first cross-desk source: one adapter feeds Defense, AI, and Energy at once,
which is what makes the convergence brief possible (D060). It queries EDGAR's
full-text search (EFTS) for a curated set of **convergence-themed probes**, each
tagged with the desk(s) it serves — the deterministic pre-filter pattern (D059)
applied to filings. A filing matching a multi-desk probe is tagged with multiple
desks; that multi-desk tag IS the convergence signal.

v1 scope: EFTS metadata only (company, ticker, CIK, form, date, accession) over
8-K material-event filings. Deferred to follow-on adapters: company-facts/XBRL
capex (per-CIK), Form 4/13F ownership (XML), full-text body extraction, and
sub-pagination (per-probe daily 8-K volume is low). Requires a descriptive
User-Agent header (SEC policy) — supplied via ``headers`` and read by the runner.
"""
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from engine.settings import settings

from .base import NormalizedRecord

_SOURCE_ID = "edgar"
_BASE_URL = "https://efts.sec.gov/LATEST/search-index"
_FORMS = "8-K"  # material-event reports — the timely, daily-cadence signal
_DEFAULT_LOOKBACK_DAYS = 7

# "Display name" is like: "NUSCALE POWER Corp  (SMR)  (CIK 0001822966)"
_DISPLAY_RE = re.compile(r"^(?P<name>.*?)\s*(?:\((?P<ticker>[^)]+)\)\s*)?\(CIK\s*(?P<cik>\d+)\)")


@dataclass(frozen=True)
class _Probe:
    query: str
    desks: tuple[str, ...]


# Convergence-themed probes (D060). Each is one EFTS phrase query; multi-desk
# probes are the cross-sector chokepoints where the thesis actually shows up.
_PROBES: tuple[_Probe, ...] = (
    _Probe("small modular reactor", ("energy", "ai")),       # AI∩Energy power
    _Probe("high-assay low-enriched uranium", ("energy",)),  # HALEU fuel chokepoint
    _Probe("hyperscale data center", ("ai", "energy")),      # AI∩Energy demand engine
    _Probe("directed energy weapon", ("defense", "energy")), # Defense∩Energy
    _Probe("counter-unmanned aircraft", ("defense", "ai")),  # Defense∩AI autonomy
    _Probe("hypersonic", ("defense",)),                      # Defense
    _Probe("autonomous weapon", ("defense", "ai")),          # Defense∩AI
    _Probe("rare earth", ("defense", "ai", "energy")),       # trilateral chokepoint
)


def _sha256(data: dict) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _parse_display_name(display: str) -> tuple[str, str | None, str | None]:
    """Return (company_name, ticker, cik) from an EFTS display_names entry."""
    m = _DISPLAY_RE.match(display.strip())
    if not m:
        return display.strip(), None, None
    return m.group("name").strip(), m.group("ticker"), m.group("cik")


class EDGARFullTextAdapter:
    source_id: str = _SOURCE_ID
    base_url: str = _BASE_URL
    http_method: str = "GET"

    def __init__(self) -> None:
        # Set per request in build_request_payload and read in parse(). The runner
        # calls build → fetch → parse sequentially on one instance, so this carries
        # the active probe's desks into parse. Defaults to the first probe so parse()
        # is usable standalone (e.g. in tests).
        self._active_probe: _Probe = _PROBES[0]

    @property
    def headers(self) -> dict:
        # SEC requires a descriptive User-Agent on every request.
        return {"User-Agent": settings.edgar_user_agent}

    @property
    def probe_count(self) -> int:
        return len(_PROBES)

    # ── parse ────────────────────────────────────────────────────────────────

    def parse(self, response: dict) -> list[NormalizedRecord]:
        hits = (response.get("hits") or {}).get("hits") or []
        desks = list(self._active_probe.desks)
        theme = self._active_probe.query
        records: list[NormalizedRecord] = []

        for hit in hits:
            src = hit.get("_source") or {}
            native_id = hit.get("_id")
            adsh = src.get("adsh")
            if not native_id or not adsh:
                continue

            display = (src.get("display_names") or [""])[0]
            company, ticker, cik = _parse_display_name(display)
            form = src.get("form") or (src.get("root_forms") or [""])[0]
            file_date = src.get("file_date")
            items = src.get("items") or []

            structured = {
                "accession": adsh,
                "cik": cik,
                "company_name": company,
                "ticker": ticker,
                "form": form,
                "file_date": file_date,
                "theme": theme,
                "items": items,
                "sics": src.get("sics") or [],
            }

            entity_mentions = []
            if company:
                entity_mentions.append({
                    "mention": company,
                    "normalized": company.upper().strip(),
                    "entity_id": None,
                    "confidence": None,
                    "resolved_by": None,
                    "ticker": ticker,
                    "cik": cik,
                })

            records.append(NormalizedRecord(
                source_id=_SOURCE_ID,
                record_type="filing",
                desk=desks,
                entity_mentions=entity_mentions,
                structured_data=structured,
                text_chunk=self._build_text_chunk(company, ticker, form, file_date, theme),
                content_hash=_sha256(structured),
                native_id=native_id,
                url=self._filing_url(cik, adsh, native_id),
                fetched_at=datetime.now(timezone.utc),
            ))
        return records

    @staticmethod
    def _build_text_chunk(company, ticker, form, file_date, theme) -> str:
        tick = f" ({ticker})" if ticker else ""
        return (
            f"SEC {form} filing by {company}{tick} on {file_date}, "
            f"referencing \"{theme}\"."
        )

    @staticmethod
    def _filing_url(cik: str | None, adsh: str, native_id: str) -> str:
        if not cik:
            return "https://www.sec.gov/cgi-bin/browse-edgar"
        accession_nodash = adsh.replace("-", "")
        filename = native_id.split(":", 1)[1] if ":" in native_id else ""
        return (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession_nodash}/{filename}"
        )

    # ── cursor / request building ──────────────────────────────────────────────

    def build_request_payload(self, cursor: dict | None, page: int = 1) -> dict:
        # page (1-based) selects the probe; the persisted cursor holds the date
        # watermark. The runner advances `page` via next_cursor until probes run out.
        probe = _PROBES[(page - 1) % len(_PROBES)]
        self._active_probe = probe

        if cursor and "last_date" in cursor:
            start_date = cursor["last_date"]
        else:
            start_date = (date.today() - timedelta(days=_DEFAULT_LOOKBACK_DAYS)).isoformat()

        return {
            "q": f'"{probe.query}"',
            "forms": _FORMS,
            "startdt": start_date,
            "enddt": date.today().isoformat(),
            "from": 0,
        }

    def next_cursor(self, response: dict, current_page: int) -> dict:
        # Walk through every probe once per run, then advance the date watermark.
        if current_page < len(_PROBES):
            return {"page": current_page + 1}
        return {"last_date": date.today().isoformat()}
