"""arXiv API adapter — the technology-advancement leg of a brief (D063, D066).

Capital-flow sources (USAspending, EDGAR) tell you where money has *already*
moved; arXiv is a **leading indicator** of where capability is moving — the
research front that capital tends to chase. It is the AI desk's depth source
(the desk USAspending+EDGAR leave starved), and it serves Defense∩AI (autonomy)
and AI∩Energy (grid/fusion ML) as convergence probes too.

Two things make this adapter different from the JSON sources:

1. **Atom XML, not JSON.** The arXiv API returns an Atom feed, so this adapter
   declares ``response_format = "text"`` and ``parse()`` takes the raw XML body
   (the runner passes the format through to :class:`HttpFetcher`).
2. **No dollar amount.** A paper has no ``amount_usd``, so it scores on novelty +
   source authority rather than magnitude. That still clears the materiality
   threshold (novelty 0.30 + authority alone ≈ 0.47 > 0.35), so research surfaces
   in briefs — it just ranks below billion-dollar awards, which is correct: a
   preprint is a *signal to watch*, not a capital event. Rich abstracts (vs.
   EDGAR's thin filing metadata) give synthesis enough to ground a faithful claim.

Probe model mirrors EDGAR/USAspending (D061/D064): each probe is one arXiv
``search_query`` tagged with the desk(s) it serves; the runner's ``page`` counter
selects the probe. The content hash is over the paper's *intrinsic* fields (id,
version, title, abstract) and excludes the probe theme, so the same paper matched
by two probes dedups to one row rather than double-storing.
"""
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .base import NormalizedRecord

_SOURCE_ID = "arxiv"
_BASE_URL = "https://export.arxiv.org/api/query"
_DEFAULT_LOOKBACK_DAYS = 7      # research is lower-velocity but arXiv volume is high
_MAX_RESULTS = 50              # per probe, most-recent-first
_ABSTRACT_CHARS = 600          # truncate the abstract in the embedded/cited chunk
_USER_AGENT = "HardPowerIntelligence/1.0 (hardpowerintelligence@gmail.com)"

# Atom + arXiv-extension XML namespaces.
_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"

_VERSION_RE = re.compile(r"(v\d+)$")


@dataclass(frozen=True)
class _Probe:
    query: str               # arXiv search_query expression
    desks: tuple[str, ...]


# Advancement probes. Pure-AI probes fill the starved AI desk; multi-desk probes
# (autonomy → Defense∩AI; grid/fusion ML → AI∩Energy) are the convergence signal.
_PROBES: tuple[_Probe, ...] = (
    # Frontier AI / scaling → AI
    _Probe(
        'cat:cs.LG AND (abs:"large language model" OR abs:"foundation model" '
        'OR abs:"scaling law")',
        ("ai",),
    ),
    # AI systems / compute / efficiency → AI
    _Probe(
        '(cat:cs.AR OR cat:cs.DC) AND (abs:"deep learning" OR abs:"neural network" '
        'OR abs:"accelerator")',
        ("ai",),
    ),
    # Autonomy & robotics → Defense∩AI
    _Probe(
        'cat:cs.RO AND (abs:"autonomous" OR abs:"unmanned" OR abs:"multi-agent")',
        ("defense", "ai"),
    ),
    # AI applied to energy systems → AI∩Energy
    _Probe(
        '(abs:"power grid" OR abs:"energy storage" OR abs:"nuclear reactor" '
        'OR abs:"fusion") AND (abs:"machine learning" OR abs:"reinforcement learning" '
        'OR abs:"deep learning")',
        ("ai", "energy"),
    ),
    # Frontier compute substrate (quantum / chips) → AI
    _Probe(
        'abs:"quantum computing" OR abs:"superconducting qubit" OR abs:"chip design"',
        ("ai",),
    ),
)


def _sha256(data: dict) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _clean(text: str | None) -> str:
    # arXiv titles/abstracts carry hard line breaks and runs of whitespace.
    return " ".join((text or "").split())


def _split_version(tail: str) -> tuple[str, str]:
    """('2406.01234v2') → ('2406.01234', 'v2'); ('hep-th/9901001') → (..., '')."""
    m = _VERSION_RE.search(tail)
    if m:
        return tail[: -len(m.group(1))], m.group(1)
    return tail, ""


class ArxivAdapter:
    source_id: str = _SOURCE_ID
    base_url: str = _BASE_URL
    http_method: str = "GET"
    response_format: str = "text"   # arXiv returns Atom XML, not JSON

    def __init__(self) -> None:
        # Set per request in build_request_payload, read in parse(); the runner calls
        # build → fetch → parse sequentially on one instance. Defaults to the first
        # probe so parse() works standalone (e.g. in tests).
        self._active_probe: _Probe = _PROBES[0]

    @property
    def headers(self) -> dict:
        # arXiv asks API clients to identify themselves and rate-limit politely.
        return {"User-Agent": _USER_AGENT}

    @property
    def probe_count(self) -> int:
        return len(_PROBES)

    # ── parse ────────────────────────────────────────────────────────────────

    def parse(self, response: str) -> list[NormalizedRecord]:
        # Encode to bytes: ElementTree refuses a str that carries an XML encoding
        # declaration (arXiv feeds start with <?xml ... encoding="UTF-8"?>).
        payload = response.encode("utf-8") if isinstance(response, str) else response
        root = ET.fromstring(payload)

        desks = list(self._active_probe.desks)
        theme = self._active_probe.query
        records: list[NormalizedRecord] = []

        for entry in root.findall(f"{_ATOM}entry"):
            id_url = _clean(entry.findtext(f"{_ATOM}id"))
            if not id_url:
                continue
            tail = id_url.rsplit("/abs/", 1)[-1] if "/abs/" in id_url else id_url.rsplit("/", 1)[-1]
            arxiv_id, version = _split_version(tail)

            title = _clean(entry.findtext(f"{_ATOM}title"))
            abstract = _clean(entry.findtext(f"{_ATOM}summary"))
            published = entry.findtext(f"{_ATOM}published")
            updated = entry.findtext(f"{_ATOM}updated")
            authors = [
                _clean(a.findtext(f"{_ATOM}name"))
                for a in entry.findall(f"{_ATOM}author")
                if _clean(a.findtext(f"{_ATOM}name"))
            ]
            primary = entry.find(f"{_ARXIV}primary_category")
            primary_cat = primary.get("term") if primary is not None else None
            categories = [
                c.get("term") for c in entry.findall(f"{_ATOM}category") if c.get("term")
            ]

            structured = {
                "arxiv_id": arxiv_id,
                "version": version,
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "primary_category": primary_cat,
                "categories": categories,
                "published": published,
                "updated": updated,
                "theme": theme,   # probe context; excluded from the hash (see below)
            }

            # Hash intrinsic paper fields only — NOT the probe theme — so the same
            # paper found by two probes dedups instead of double-storing. A new
            # version (revised abstract/version tag) is genuinely new content.
            content_hash = _sha256({
                "arxiv_id": arxiv_id,
                "version": version,
                "title": title,
                "abstract": abstract,
            })

            entity_mentions = []
            if authors:
                lead = authors[0]
                entity_mentions.append({
                    "mention": lead,
                    "normalized": lead.upper().strip(),
                    "entity_id": None,
                    "confidence": None,
                    "resolved_by": None,
                    "entity_type": "person",   # author, not a company (materiality weight)
                })

            records.append(NormalizedRecord(
                source_id=_SOURCE_ID,
                record_type="research_paper",
                desk=desks,
                entity_mentions=entity_mentions,
                structured_data=structured,
                text_chunk=self._build_text_chunk(title, primary_cat, published, authors, abstract),
                content_hash=content_hash,
                native_id=arxiv_id,
                url=f"https://arxiv.org/abs/{arxiv_id}",
                fetched_at=datetime.now(timezone.utc),
            ))
        return records

    @staticmethod
    def _build_text_chunk(title, primary_cat, published, authors, abstract) -> str:
        who = ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")
        when = (published or "")[:10]
        cat = f"{primary_cat} " if primary_cat else ""
        body = abstract[:_ABSTRACT_CHARS] + ("…" if len(abstract) > _ABSTRACT_CHARS else "")
        parts = [
            f'arXiv {cat}paper "{title}"',
            f"({when})" if when else "",
            f"by {who}." if who else "",
            f"Abstract: {body}" if body else "",
        ]
        return " ".join(p for p in parts if p)

    # ── cursor / request building ──────────────────────────────────────────────

    def build_request_payload(self, cursor: dict | None, page: int = 1) -> dict:
        # page (1-based) selects the probe; the persisted cursor holds the date
        # watermark. The runner advances `page` via next_cursor until probes run out.
        probe = _PROBES[(page - 1) % len(_PROBES)]
        self._active_probe = probe

        if cursor and "last_date" in cursor:
            start = date.fromisoformat(cursor["last_date"])
        else:
            start = date.today() - timedelta(days=_DEFAULT_LOOKBACK_DAYS)

        lo = start.strftime("%Y%m%d") + "0000"
        hi = date.today().strftime("%Y%m%d") + "2359"
        search_query = f"({probe.query}) AND submittedDate:[{lo} TO {hi}]"

        return {
            "search_query": search_query,
            "start": 0,
            "max_results": _MAX_RESULTS,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

    def next_cursor(self, response, current_page: int) -> dict:
        # Walk every probe once per run, then advance the date watermark.
        if current_page < len(_PROBES):
            return {"page": current_page + 1}
        return {"last_date": date.today().isoformat()}
