"""NRC adapter via the Federal Register API — the regulatory leg of the Energy desk (D095).

The Energy desk is consistently the thinnest (Phase B, 2026-06-19): the capital-flow
sources (USAspending grants, EDGAR filings) and arXiv leave it starved of *regulatory*
signal. The U.S. Nuclear Regulatory Commission is where the nuclear/SMR convergence thesis
actually plays out as enforceable events — a combined-license application, an advanced-reactor
rule, a HALEU fuel decision — months before the money or the 8-K shows up. This adapter pulls
those events from the **Federal Register API** (free, no key, public-domain) filtered to NRC.

Shape mirrors the other probe adapters (EDGAR/USAspending/arXiv, D061/D063/D066): each probe is
one on-thesis search term within NRC documents, tagged to the Energy desk; the runner's ``page``
counter walks the probes. A regulatory document has no dollar amount, so — like arXiv — it scores
on **source authority + novelty** rather than magnitude (``source_weights['nrc']`` is high because
the NRC is the authoritative nuclear regulator), which clears the materiality floor comfortably.
The synthesis model classifies these as ``policy`` items from the text.

Two deliberate design choices:
  * **Entity linking via a curated ticker allowlist (D096).** NRC documents carry no ticker/CIK/UEI,
    and name-only trigram matching is fragile for short names (``"Oklo"`` scores below the resolver's
    0.92 gate). So instead we attach a KNOWN ticker when a thesis-relevant public nuclear/fuel-cycle
    company is named, and resolve via the exact-identifier path — the resolver's strongest,
    false-link-proof route. A name not on the allowlist simply produces no mention (no false link).
    This is what lets an NRC notice about Oklo or Centrus produce an entity chip and feed cross-desk
    convergence, the same way an EDGAR filing or a USAspending award does.
  * **Fixed rolling lookback, not a forward watermark.** Federal Register publication dates don't
    lag, but a forward-advancing watermark is the trap that silently zeroed USAspending (Phase B);
    a fixed lookback + content-hash dedup is the robust pattern, so we use it here too.
"""
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .base import NormalizedRecord

_SOURCE_ID = "nrc"
_BASE_URL = "https://www.federalregister.gov/api/v1/documents.json"
_AGENCY_SLUG = "nuclear-regulatory-commission"
_LOOKBACK_DAYS = 7          # FR pub dates don't lag; 7d spans weekends + the daily cron, dedup absorbs repeats
_PER_PAGE = 20              # most-recent-first within each probe term
_ABSTRACT_CHARS = 700       # truncate the abstract in the cited chunk
_USER_AGENT = "HardPowerIntelligence/1.0 (hardpowerintelligence@gmail.com)"

# Fields requested from the API (smaller payload, stable parse surface).
_FIELDS = [
    "document_number", "title", "type", "abstract", "html_url", "publication_date", "agencies",
]


@dataclass(frozen=True)
class _Probe:
    term: str                # Federal Register full-text search term (within NRC docs)
    desks: tuple[str, ...]


@dataclass(frozen=True)
class _NuclearEntity:
    display: str             # clean mention/display name
    ticker: str              # exact identifier used to resolve (must be seeded to link)
    aliases: tuple[str, ...]  # lowercase forms matched word-bounded in title + abstract


# Curated public nuclear / fuel-cycle entities for precision-first linking (D096). We resolve via the
# EXACT-ticker path (false-link-proof) rather than fuzzy name trigram, so only clearly-named public
# players whose cross-desk presence makes convergence meaningful are listed; a name not here yields no
# mention. An attached ticker that isn't seeded simply fails to resolve (no false link). Extend freely.
_NUCLEAR_ENTITIES: tuple[_NuclearEntity, ...] = (
    _NuclearEntity("Oklo", "OKLO", ("oklo",)),
    _NuclearEntity("NuScale Power", "SMR", ("nuscale",)),
    _NuclearEntity("Centrus Energy", "LEU", ("centrus",)),
    _NuclearEntity("BWX Technologies", "BWXT", ("bwx technologies", "bwxt")),
    _NuclearEntity("Constellation Energy", "CEG", ("constellation energy", "constellation")),
    _NuclearEntity("Vistra", "VST", ("vistra",)),
    _NuclearEntity("Nano Nuclear Energy", "NNE", ("nano nuclear",)),
    _NuclearEntity("Energy Fuels", "UUUU", ("energy fuels",)),
    _NuclearEntity("Uranium Energy", "UEC", ("uranium energy",)),
    _NuclearEntity("Cameco", "CCJ", ("cameco",)),
    _NuclearEntity("Lightbridge", "LTBR", ("lightbridge",)),
    _NuclearEntity("GE Vernova", "GEV", ("ge vernova",)),
)


def _extract_nuclear_mentions(text: str) -> list[dict]:
    """Best-effort, precision-first entity mentions from a document's text (title + abstract).

    Each allowlisted company named in the text yields one mention carrying its ticker, which the
    linker (``extract_resolution_inputs``) resolves via the exact-identifier path. At most one mention
    per ticker per record. Shape mirrors the other adapters' mention dicts.
    """
    low = text.lower()
    mentions: list[dict] = []
    seen: set[str] = set()
    for ent in _NUCLEAR_ENTITIES:
        if ent.ticker in seen:
            continue
        if any(re.search(rf"\b{re.escape(alias)}\b", low) for alias in ent.aliases):
            mentions.append({
                "mention": ent.display,
                "normalized": ent.display.upper(),
                "ticker": ent.ticker,
                "entity_id": None,
                "confidence": None,
                "resolved_by": None,
                "entity_type": "company",
            })
            seen.add(ent.ticker)
    return mentions


# On-thesis nuclear-development probes. Each is a substantive regulatory event class — not routine
# license-amendment / meeting minutiae — so the pre-filter does the curation the significance gate
# (D085) would otherwise spend an LLM call on. All tag Energy; nuclear is the desk's convergence core.
_PROBES: tuple[_Probe, ...] = (
    _Probe("small modular reactor", ("energy",)),
    _Probe("advanced reactor", ("energy",)),
    _Probe("high-assay low-enriched uranium", ("energy",)),   # HALEU fuel supply (Centrus/Oklo)
    _Probe("combined license", ("energy",)),                   # new-reactor build authorization
    _Probe("uranium enrichment", ("energy",)),                 # fuel-cycle / enrichment capacity
    _Probe("microreactor", ("energy",)),                       # MMR licensing (eVinci/KRONOS/XENITH)
    _Probe("TRISO", ("energy",)),                              # TRISO particle-fuel qualification
)


def _sha256(data: dict) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


class NRCAdapter:
    source_id: str = _SOURCE_ID
    base_url: str = _BASE_URL
    http_method: str = "GET"
    response_format: str = "json"

    def __init__(self) -> None:
        # Set per request in build_request_payload, read in parse(); the runner calls
        # build → fetch → parse sequentially on one instance. Defaults to the first probe
        # so parse() works standalone (e.g. in tests).
        self._active_probe: _Probe = _PROBES[0]

    @property
    def headers(self) -> dict:
        return {"User-Agent": _USER_AGENT}

    @property
    def probe_count(self) -> int:
        return len(_PROBES)

    @property
    def max_pages(self) -> int:
        # One API page per probe; the bound is the probe count, not the global default
        # (mirrors EDGAR). The runner stops earlier once next_cursor stops advancing.
        return len(_PROBES)

    # ── parse ────────────────────────────────────────────────────────────────────

    def parse(self, response: dict) -> list[NormalizedRecord]:
        desks = list(self._active_probe.desks)
        term = self._active_probe.term
        records: list[NormalizedRecord] = []

        for row in response.get("results", []):
            document_number = _clean(row.get("document_number"))
            title = _clean(row.get("title"))
            if not document_number or not title:
                continue

            doc_type = _clean(row.get("type"))            # Rule | Proposed Rule | Notice | …
            abstract = _clean(row.get("abstract"))
            publication_date = _clean(row.get("publication_date"))
            html_url = _clean(row.get("html_url"))
            agency = _agency_name(row.get("agencies"))

            structured = {
                "document_number": document_number,
                "title": title,
                "doc_type": doc_type,
                "abstract": abstract,
                "publication_date": publication_date,
                "agency": agency,
                "html_url": html_url,
                "term": term,        # probe context; excluded from the hash (see below)
            }

            # Hash intrinsic document fields only — NOT the probe term — so the same document
            # surfaced by two probes dedups to one row instead of double-storing.
            content_hash = _sha256({
                "document_number": document_number,
                "title": title,
                "abstract": abstract,
            })

            records.append(NormalizedRecord(
                source_id=_SOURCE_ID,
                record_type="regulatory_document",
                desk=desks,
                # Precision-first linking (D096): allowlisted public nuclear companies named in the
                # title/abstract, carrying a ticker the linker resolves via the exact-identifier path.
                entity_mentions=_extract_nuclear_mentions(f"{title} {abstract}"),
                structured_data=structured,
                text_chunk=self._build_text_chunk(doc_type, title, agency, publication_date, abstract),
                content_hash=content_hash,
                native_id=document_number,
                url=html_url or f"https://www.federalregister.gov/d/{document_number}",
                fetched_at=datetime.now(timezone.utc),
            ))
        return records

    @staticmethod
    def _build_text_chunk(doc_type, title, agency, publication_date, abstract) -> str:
        kind = doc_type or "document"
        who = agency or "Nuclear Regulatory Commission"
        when = f" ({publication_date})" if publication_date else ""
        body = abstract[:_ABSTRACT_CHARS] + ("…" if len(abstract) > _ABSTRACT_CHARS else "")
        parts = [
            f'{who} {kind}{when}: "{title}".',
            f"Summary: {body}" if body else "",
        ]
        return " ".join(p for p in parts if p)

    # ── cursor / request building ──────────────────────────────────────────────────

    def build_request_payload(self, cursor: dict | None, page: int = 1) -> dict:
        # page (1-based) selects the probe; the window is always a fixed rolling lookback
        # (no forward watermark — that trap silently zeroed USAspending, Phase B). Dedup
        # absorbs the repeats across runs.
        probe = _PROBES[(page - 1) % len(_PROBES)]
        self._active_probe = probe

        gte = (date.today() - timedelta(days=_LOOKBACK_DAYS)).isoformat()

        return {
            "conditions[agencies][]": _AGENCY_SLUG,
            "conditions[term]": probe.term,
            "conditions[publication_date][gte]": gte,
            "order": "newest",
            "per_page": _PER_PAGE,
            "fields[]": _FIELDS,
        }

    def next_cursor(self, response, current_page: int) -> dict:
        # Walk every probe once per run, then advance the date watermark.
        if current_page < len(_PROBES):
            return {"page": current_page + 1}
        return {"last_date": date.today().isoformat()}


def _agency_name(agencies) -> str:
    """Pull a display agency name from the API's agencies array; tolerant of shape."""
    if isinstance(agencies, list) and agencies:
        first = agencies[0]
        if isinstance(first, dict):
            return _clean(first.get("name") or first.get("raw_name"))
    return ""
