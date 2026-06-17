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
import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import structlog

from engine.settings import settings

from .base import NormalizedRecord
from .edgar_body import build_enriched_chunk, extract_facts, strip_html

log = structlog.get_logger()

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


# Convergence-themed probes (D060, widened D077). Each is one EFTS phrase query;
# multi-desk probes are the cross-sector chokepoints where the thesis actually shows
# up. EFTS has no regex/wildcards — only exact phrases and boolean OR — so breadth
# comes from MORE probes, and one phrase per probe preserves clean theme + desk
# attribution (D059). The first 8 are the original set (their page positions are
# pinned by tests); everything after widens coverage so a sparse desk has enough
# fresh, fact-dense filings to clear the provable-claim floor on a slow day (D076).
_PROBES: tuple[_Probe, ...] = (
    # ── Original 8 (positions pinned: page 1 = SMR, page 8 = rare earth) ──────────
    _Probe("small modular reactor", ("energy", "ai")),       # AI∩Energy power
    _Probe("high-assay low-enriched uranium", ("energy",)),  # HALEU fuel chokepoint
    _Probe("hyperscale data center", ("ai", "energy")),      # AI∩Energy demand engine
    _Probe("directed energy weapon", ("defense", "energy")), # Defense∩Energy
    _Probe("counter-unmanned aircraft", ("defense", "ai")),  # Defense∩AI autonomy
    _Probe("hypersonic", ("defense",)),                      # Defense
    _Probe("autonomous weapon", ("defense", "ai")),          # Defense∩AI
    _Probe("rare earth", ("defense", "ai", "energy")),       # trilateral chokepoint
    # ── Energy depth ─────────────────────────────────────────────────────────────
    _Probe("grid-scale storage", ("energy", "ai")),          # AI load ↔ storage
    _Probe("battery energy storage", ("energy",)),
    _Probe("transmission interconnection", ("energy", "ai")),# the data-center queue
    _Probe("power purchase agreement", ("energy", "ai")),    # hyperscaler PPAs
    _Probe("liquefied natural gas", ("energy",)),
    _Probe("uranium enrichment", ("energy", "defense")),     # fuel ↔ naval/defense
    _Probe("nuclear fuel", ("energy", "defense")),
    _Probe("solid-state battery", ("energy", "ai")),
    _Probe("geothermal", ("energy", "ai")),                  # firm power for compute
    _Probe("microgrid", ("energy", "defense")),              # base/installation resilience
    # ── Defense depth ────────────────────────────────────────────────────────────
    _Probe("munitions production", ("defense",)),
    _Probe("missile defense", ("defense",)),
    _Probe("loitering munition", ("defense", "ai")),
    _Probe("unmanned surface vessel", ("defense", "ai")),
    _Probe("solid rocket motor", ("defense",)),
    _Probe("electronic warfare", ("defense",)),
    _Probe("satellite constellation", ("defense", "ai")),
    _Probe("shipbuilding", ("defense",)),
    _Probe("Defense Production Act", ("defense", "energy")),
    # ── AI / compute depth ───────────────────────────────────────────────────────
    _Probe("generative artificial intelligence", ("ai",)),
    _Probe("large language model", ("ai",)),
    _Probe("graphics processing unit", ("ai", "energy")),    # GPUs ↔ power draw
    _Probe("semiconductor fabrication", ("ai", "defense")),
    _Probe("advanced packaging", ("ai",)),                   # chiplets/HBM
    _Probe("liquid cooling", ("ai", "energy")),              # data-center thermal
    _Probe("edge computing", ("ai", "defense")),
    # ── Trilateral chokepoints (the convergence core) ────────────────────────────
    _Probe("rare earth magnet", ("defense", "ai", "energy")),
    _Probe("permanent magnet", ("defense", "energy")),
    _Probe("gallium", ("defense", "ai", "energy")),          # semis + export controls
    _Probe("germanium", ("defense", "ai", "energy")),
    _Probe("critical minerals", ("defense", "ai", "energy")),
    _Probe("quantum computing", ("defense", "ai")),
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

    @property
    def max_pages(self) -> int:
        # One page per probe — the runner reads this so the global ingest_max_pages
        # safety cap (10) doesn't silently truncate the widened probe set (D077).
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

    # ── body enrichment (D078) ─────────────────────────────────────────────────

    async def enrich(self, records: list[NormalizedRecord], fetcher) -> list[NormalizedRecord]:
        """Fetch each filing's document and fold its facts into the record (D078).

        The runner calls this after :meth:`parse`, before persist. For each record we
        GET the filing body, strip HTML, extract dollar amounts / dates / percentages,
        set ``structured_data['amount_usd']`` (so the materiality scorer can magnitude-
        rank it) and rebuild ``text_chunk`` with a substantive, citable excerpt. Bounded
        by ``edgar_max_bodies_per_run``; any fetch/parse failure leaves the metadata
        record intact (best-effort enrichment never drops a record)."""
        if not settings.edgar_fetch_bodies:
            return records

        fetched = 0
        for rec in records:
            if fetched >= settings.edgar_max_bodies_per_run:
                break
            url = rec.url
            if not url or "browse-edgar" in url:  # no resolvable document (no CIK)
                continue
            try:
                raw = await fetcher.fetch_json(
                    "GET", url, headers=self.headers, response_format="text"
                )
                body = strip_html(raw if isinstance(raw, str) else "")
                if not body:
                    continue
                facts = extract_facts(body)
                rec.text_chunk = build_enriched_chunk(
                    rec.text_chunk, body, facts,
                    excerpt_chars=settings.edgar_body_excerpt_chars,
                )
                rec.structured_data["body_amounts_usd"] = facts.amounts_usd[:25]
                rec.structured_data["body_dates"] = facts.dates[:25]
                if facts.max_amount_usd is not None:
                    rec.structured_data["amount_usd"] = facts.max_amount_usd
                fetched += 1
                await asyncio.sleep(0.15)  # ~7/s — under SEC's 10 req/s courtesy limit
            except Exception as exc:  # noqa: BLE001 — body is best-effort; keep metadata
                log.warning("edgar_body_failed", url=url, error=str(exc)[:200])
                continue

        log.info("edgar_bodies_enriched", fetched=fetched, total=len(records))
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
