"""SEC EDGAR full-text search adapter (D055 §10, D060).

The first cross-desk source: one adapter feeds Defense, AI, and Energy at once,
which is what makes the convergence brief possible (D060). It queries EDGAR's
full-text search (EFTS) for a curated set of **convergence-themed probes**, each
tagged with the desk(s) it serves — the deterministic pre-filter pattern (D059)
applied to filings. A filing matching a multi-desk probe is tagged with multiple
desks; that multi-desk tag IS the convergence signal.

Scope: EFTS hits over **8-K** material-event filings and **Form D** Reg D private
placements (D081). ``enrich()`` then fetches each document — 8-K HTML bodies mined for
amounts/dates/% (D078), Form D ``primary_doc.xml`` mined for the offering size — so
records carry checkable facts, not just metadata. Still deferred: company-facts/XBRL
capex (per-CIK), Form 4/13F ownership, and sub-pagination. Requires a descriptive
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
from .edgar_body import (
    build_enriched_chunk,
    build_form_d_chunk,
    extract_facts,
    extract_form_d_facts,
    strip_html,
)

log = structlog.get_logger()

_SOURCE_ID = "edgar"
_BASE_URL = "https://efts.sec.gov/LATEST/search-index"
# 8-K = timely material events; D = Reg D private placements (D081) — the private-capital
# formation signal (offering size lives in the Form D XML, mined in enrich()).
_FORMS = "8-K,D"
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
    # Tightened (curation Step 2, D085 desk identity): these are energy-PRIMARY. Their AI link
    # was only demand-side ("compute needs power"), which diluted the AI desk with generic energy
    # project finance (a solar+storage farm, a PPA, a wind buy landing on "AI Infrastructure").
    # So the `ai` tag is dropped here. Genuinely compute-coupled power probes keep AI elsewhere:
    # hyperscale data center, liquid cooling, GPU (below), and SMR (data-center nuclear, above).
    _Probe("grid-scale storage", ("energy",)),
    _Probe("battery energy storage", ("energy",)),
    _Probe("transmission interconnection", ("energy",)),
    _Probe("power purchase agreement", ("energy",)),
    _Probe("liquefied natural gas", ("energy",)),
    _Probe("uranium enrichment", ("energy", "defense")),     # fuel ↔ naval/defense
    _Probe("nuclear fuel", ("energy", "defense")),
    _Probe("solid-state battery", ("energy",)),
    _Probe("geothermal", ("energy",)),
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
    # ── Cutting-edge fronts (operator topic review, 2026-06-28) ───────────────────
    # Append-only (positions after the pinned 8); desk[0] is the home desk (D097).
    # Defense — autonomy, directed energy, space, quantum/PNT:
    _Probe("collaborative combat aircraft", ("defense", "ai")),  # CCA / loyal wingman
    _Probe("high-power microwave", ("defense",)),                # HPM counter-swarm
    _Probe("high-energy laser", ("defense",)),                   # HEL (cost-per-shot)
    _Probe("unmanned underwater vehicle", ("defense", "ai")),    # UUV / XLUUV
    _Probe("quantum sensing", ("defense", "ai")),                # alternative PNT
    _Probe("space situational awareness", ("defense", "ai")),    # SSA / space control
    # AI — memory, photonics, lithography, cooling:
    _Probe("high bandwidth memory", ("ai",)),                    # HBM3e / HBM4
    _Probe("silicon photonics", ("ai",)),                        # optical interconnect/compute
    _Probe("extreme ultraviolet lithography", ("ai",)),          # High-NA EUV chokepoint
    _Probe("immersion cooling", ("ai", "energy")),               # data-center thermal
    # Energy — micro-nuclear, advanced geothermal, next-gen storage, grid:
    _Probe("microreactor", ("energy",)),                         # MMR / nuclear battery
    _Probe("enhanced geothermal", ("energy",)),                  # EGS / closed-loop
    _Probe("perovskite", ("energy",)),                           # tandem solar
    _Probe("iron-air battery", ("energy",)),                     # multi-day LDES
    _Probe("long-duration energy storage", ("energy",)),         # LDES
    _Probe("virtual power plant", ("energy",)),                  # VPP / grid orchestration
    # Space ∩ Energy ∩ AI convergence — the thesis core (SBSP / compute-in-space):
    _Probe("space-based solar power", ("energy", "ai")),         # SBSP / power beaming
    _Probe("orbital data center", ("ai", "energy")),            # compute-in-space inference
    # ── Remaining fronts top-up (D103) ──
    # Defense — contested logistics:
    _Probe("contested logistics", ("defense",)),                 # far-forward sustainment
    _Probe("biomanufacturing", ("defense", "energy")),           # synthetic-bio supply / biofuels
    # AI — networking fabric:
    _Probe("optical circuit switching", ("ai",)),                # OCS data-center networking
    _Probe("data processing unit", ("ai",)),                     # DPU / SmartNIC offload
    _Probe("Ultra Ethernet", ("ai",)),                           # UEC scale-out fabric
    # Energy — next-gen hydro, grid-component crunch:
    _Probe("hydrokinetic", ("energy",)),                         # ultra-low-head hydro/tidal
    _Probe("grid transformer shortage", ("energy",)),            # transformer/copper crunch
)


def themes_for_desk(desk: str) -> list[str]:
    """The convergence probe phrases serving a desk (D082) — reused as the GDELT
    attention-signal themes so the Signal tracks the same vocabulary the desk is built on."""
    return [p.query for p in _PROBES if desk in p.desks]


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
        """Fetch each filing's document and fold its facts into the record (D078, D081).

        The runner calls this after :meth:`parse`, before persist. An 8-K is mined from
        its HTML body (dollar amounts / dates / percentages); a Form D is mined from its
        structured ``primary_doc.xml`` for the offering size (the private-capital signal,
        D081). Both set ``structured_data['amount_usd']`` so the materiality scorer can
        magnitude-rank the record, and rebuild ``text_chunk`` with citable specifics.
        Bounded by ``edgar_max_bodies_per_run``; any fetch/parse failure leaves the
        metadata record intact (best-effort enrichment never drops a record)."""
        if not settings.edgar_fetch_bodies:
            return records

        fetched = 0
        for rec in records:
            if fetched >= settings.edgar_max_bodies_per_run:
                break
            try:
                if (rec.structured_data.get("form") or "").upper().startswith("D"):
                    hit = await self._enrich_form_d(rec, fetcher)
                else:
                    hit = await self._enrich_body(rec, fetcher)
                if hit:
                    fetched += 1
                    await asyncio.sleep(0.15)  # ~7/s — under SEC's 10 req/s courtesy
            except Exception as exc:  # noqa: BLE001 — enrichment is best-effort; keep metadata
                log.warning("edgar_enrich_failed", url=rec.url, error=str(exc)[:200])
                continue

        log.info("edgar_bodies_enriched", fetched=fetched, total=len(records))
        return records

    async def _enrich_body(self, rec: NormalizedRecord, fetcher) -> bool:
        """8-K HTML body → amounts/dates/% (D078). Returns True if it fetched a body."""
        url = rec.url
        if not url or "browse-edgar" in url:  # no resolvable document (no CIK)
            return False
        raw = await fetcher.fetch_json("GET", url, headers=self.headers, response_format="text")
        body = strip_html(raw if isinstance(raw, str) else "")
        if not body:
            return False
        facts = extract_facts(body)
        rec.text_chunk = build_enriched_chunk(
            rec.text_chunk, body, facts, excerpt_chars=settings.edgar_body_excerpt_chars
        )
        rec.structured_data["body_amounts_usd"] = facts.amounts_usd[:25]
        rec.structured_data["body_dates"] = facts.dates[:25]
        if facts.max_amount_usd is not None:
            rec.structured_data["amount_usd"] = facts.max_amount_usd
        return True

    async def _enrich_form_d(self, rec: NormalizedRecord, fetcher) -> bool:
        """Form D primary_doc.xml → offering size (D081). Returns True if it fetched."""
        cik = rec.structured_data.get("cik")
        adsh = rec.structured_data.get("accession")
        if not cik or not adsh:
            return False
        raw = await fetcher.fetch_json(
            "GET", self._form_d_xml_url(cik, adsh),
            headers=self.headers, response_format="text",
        )
        fd = extract_form_d_facts(raw if isinstance(raw, str) else "")
        rec.text_chunk = build_form_d_chunk(
            rec.structured_data.get("company_name") or "",
            rec.structured_data.get("ticker"), fd,
        )
        rec.structured_data["form_d"] = {
            "total_offering_usd": fd.total_offering_usd,
            "total_sold_usd": fd.total_sold_usd,
            "industry": fd.industry,
        }
        if fd.amount_usd is not None:
            rec.structured_data["amount_usd"] = fd.amount_usd
        return True

    @staticmethod
    def _form_d_xml_url(cik: str, adsh: str) -> str:
        # Form D's structured primary document lives at a stable path per accession.
        return (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{adsh.replace('-', '')}/primary_doc.xml"
        )

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
