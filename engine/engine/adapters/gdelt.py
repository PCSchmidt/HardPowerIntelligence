"""GDELT-as-story adapter — worldwide news radar across all three desks (D101).

GDELT indexes global news in ~real time; it is the single biggest free, worldwide
store of on-thesis developments. Until now HPI used it only as an aggregate momentum
*signal* (D082) because the old "every claim cites the public record" doctrine had no
lane for un-vetted third-party reporting. The epistemic flip (D098/D099) opened that
lane: content can now enter a brief carrying a *confidence label* instead of being
excluded. So GDELT articles flow in as **Speculative**, link-only stories — the radar
that fills out a comprehensive desk read (D100) below the primary-record spine.

Deliberate guardrails (the role D055/D082 fixed, unchanged):
  * **Speculative tier, link-only.** ``source_id="gdelt"`` ⇒ ``source_weights`` 0.5 (low —
    it never crowds out a primary record) and ``epistemics.evidence_class`` = signal ⇒ the
    item is labeled SPECULATIVE regardless of citation support. ``license_class`` is
    ``scrape_gray``: we store/cite the **title** and link only, never article body text
    (the DOC 2.0 ArtList API returns only the title, so this is structural, not just policy).
  * **On-thesis, bounded.** One curated query per desk-theme (not a generic news firehose),
    English-only, ``maxrecords`` capped per probe — so volume stays bounded and relevant.
    The significance gate (D085) still judges each item.
  * **No entity links yet.** The DOC API exposes no structured entities; per-article NER is
    deferred (the BigQuery GKG backend's V2Organizations/V2Persons is the future upgrade,
    D082) — so ``entity_mentions`` is empty and these simply don't feed the graph yet.

Shape mirrors the probe adapters (NRC/EDGAR): each probe is one on-thesis query tagged to
its single home desk (clean D097 demarcation); the runner's ``page`` counter walks them.
Backend is the keyless DOC 2.0 ArtList API (no GCP); a richer BigQuery GKG backend can
replace the fetch layer later without changing the brief-side contract.
"""
import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timezone

from .base import NormalizedRecord

_SOURCE_ID = "gdelt"
_BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
_MAXRECORDS = 15          # articles per probe (most-recent-first); bounds volume per run
_TIMESPAN = "2d"          # ~matches the 48h brief window; dedup absorbs cross-run repeats
_TITLE_CHARS = 300        # cap the stored/cited title length (scrape_gray: title + link only)


@dataclass(frozen=True)
class _Probe:
    query: str               # GDELT DOC full-text query (exact phrase)
    desk: str                # single home desk (D097 demarcation)


# Curated, on-thesis news queries — one home desk each. Decoupled from the EDGAR filing
# probes on purpose: GDELT searches global *news* vocabulary, not filing text. Organized to
# systematically cover the cutting-edge topic clusters in each desk's domain (operator topic
# review, 2026-06-28) — extend freely as the fronts move.
_PROBES: tuple[_Probe, ...] = (
    # ── Defense ── unmanned/autonomy, directed energy, hypersonics/missile defense,
    # space, quantum/PNT, applied military AI (the DoD's official tech pillars).
    _Probe("collaborative combat aircraft", "defense"),     # CCA / "loyal wingman"
    _Probe("military drone swarm", "defense"),               # swarm intelligence
    _Probe("unmanned underwater vehicle", "defense"),        # UUV / XLUUV
    _Probe("unmanned surface vessel", "defense"),            # USV
    _Probe("high-energy laser weapon", "defense"),           # HEL
    _Probe("high-power microwave weapon", "defense"),        # HPM
    _Probe("hypersonic missile", "defense"),                 # HGV / scramjet
    _Probe("missile defense system", "defense"),             # "Golden Dome" architecture
    _Probe("quantum sensing navigation", "defense"),         # alternative PNT / quantum
    _Probe("proliferated low earth orbit", "defense"),       # pLEO constellations
    _Probe("space situational awareness", "defense"),        # SSA / space control
    _Probe("military artificial intelligence", "defense"),   # applied AI / Maven / agentic
    # ── AI ── accelerators, memory/packaging, networking, photonics, data-center power,
    # cooling, lithography (the compute build-out stack).
    _Probe("Nvidia Blackwell", "ai"),                        # next-gen GPU
    _Probe("AI accelerator chip", "ai"),                     # ASIC / custom silicon
    _Probe("Google TPU", "ai"),                              # hyperscaler custom silicon
    _Probe("high bandwidth memory", "ai"),                   # HBM3e / HBM4
    _Probe("advanced chip packaging", "ai"),                 # CoWoS / interposer
    _Probe("silicon photonics", "ai"),                       # optical / photonic chips
    _Probe("AI data center", "ai"),                          # buildout / superfactory
    _Probe("data center power demand", "ai"),                # grid coupling
    _Probe("immersion cooling", "ai"),                       # thermal management
    _Probe("liquid cooling data center", "ai"),              # direct-to-chip
    _Probe("EUV lithography", "ai"),                         # High-NA EUV supply chokepoint
    _Probe("AI inference chip", "ai"),                       # inference / LPU
    # ── Energy ── micro-nuclear, advanced geothermal, next-gen solar, short- and
    # long-duration storage, grid orchestration, fuel cycle.
    _Probe("small modular reactor", "energy"),               # SMR
    _Probe("nuclear microreactor", "energy"),                # MMR (eVinci / KRONOS / XENITH)
    _Probe("TRISO nuclear fuel", "energy"),                  # TRISO particle fuel
    _Probe("enhanced geothermal", "energy"),                 # EGS / closed-loop
    _Probe("perovskite solar cell", "energy"),               # tandem solar
    _Probe("nickel-zinc battery", "energy"),                 # data-center transient buffering
    _Probe("iron-air battery", "energy"),                    # multi-day LDES
    _Probe("long-duration energy storage", "energy"),        # LDES broadly
    _Probe("thermal energy storage", "energy"),              # TES
    _Probe("virtual power plant", "energy"),                 # VPP / grid orchestration
    _Probe("grid interconnection queue", "energy"),          # interconnection / load growth
    _Probe("uranium enrichment", "energy"),                  # HALEU / fuel cycle
    # ── Space ∩ Energy ∩ AI convergence (operator add, 2026-06-28) ──
    _Probe("space-based solar power", "energy"),             # SBSP / power beaming to Earth
    _Probe("space solar power beaming", "energy"),           # microwave/laser rectenna
    _Probe("orbital data center", "ai"),                     # compute-in-space / inference
    # ── Remaining fronts (top-up, D103) ──
    # Defense — contested logistics, cyber-EM:
    _Probe("contested logistics", "defense"),                # far-forward sustainment
    _Probe("military biomanufacturing", "defense"),          # synthetic-bio point-of-need supply
    _Probe("autonomous military resupply", "defense"),       # cargo drones / autonomous convoys
    _Probe("cyber electromagnetic warfare", "defense"),      # cyber-EW convergence
    # AI — networking fabric, LPU, model efficiency:
    _Probe("Nvidia NVLink interconnect", "ai"),              # NVLink / UALink scale-up fabric
    _Probe("Ultra Ethernet AI networking", "ai"),            # UEC vs InfiniBand scale-out
    _Probe("optical circuit switching", "ai"),               # OCS data-center networking
    _Probe("data processing unit", "ai"),                    # DPU / SmartNIC offload
    _Probe("Groq inference chip", "ai"),                     # LPU / static-scheduling inference
    _Probe("mixture of experts model", "ai"),                # MoE efficiency architecture
    # Energy — next-gen hydro, geothermal, grid-component crunch:
    _Probe("hydrokinetic turbine", "energy"),                # ultra-low-head hydro
    _Probe("closed-loop geothermal", "energy"),              # advanced/radiator geothermal
    _Probe("grid transformer shortage", "energy"),           # high-voltage transformer/copper crunch
)


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


class GDELTAdapter:
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
    def probe_count(self) -> int:
        return len(_PROBES)

    @property
    def max_pages(self) -> int:
        # One API call per probe; the bound is the probe count (mirrors NRC/EDGAR). The
        # runner stops earlier once next_cursor stops advancing.
        return len(_PROBES)

    # ── parse ────────────────────────────────────────────────────────────────────

    def parse(self, response: dict) -> list[NormalizedRecord]:
        desk = self._active_probe.desk
        query = self._active_probe.query
        records: list[NormalizedRecord] = []

        for art in (response or {}).get("articles", []):
            url = _clean(art.get("url"))
            title = _clean(art.get("title"))[:_TITLE_CHARS]
            if not url or not title:
                continue
            # English-only for now (quality + cost); adaptable when we vet more languages.
            language = _clean(art.get("language"))
            if language and language.lower() != "english":
                continue

            domain = _clean(art.get("domain"))
            seendate = _clean(art.get("seendate"))
            sourcecountry = _clean(art.get("sourcecountry"))

            structured = {
                "title": title,
                "domain": domain,
                "seendate": seendate,
                "sourcecountry": sourcecountry,
                "language": language,
                "url": url,
                "query": query,        # probe context; excluded from the hash (see below)
            }

            # Hash the intrinsic article identity (url + title), NOT the probe query — so the
            # same article surfaced by two probes dedups to one row.
            content_hash = hashlib.sha256(f"{url}\n{title}".encode()).hexdigest()

            records.append(NormalizedRecord(
                source_id=_SOURCE_ID,
                record_type="news",
                desk=[desk],
                # No entity links yet — the DOC API exposes no structured entities; per-article
                # NER / BigQuery GKG entities is the deferred upgrade (D082). Empty = unlinked.
                entity_mentions=[],
                structured_data=structured,
                # scrape_gray: title + attribution + link only, NEVER article body text (which
                # the DOC API doesn't return anyway). The reader links out to the source.
                text_chunk=self._build_text_chunk(domain, seendate, title),
                content_hash=content_hash,
                native_id=url,
                url=url,
                fetched_at=datetime.now(timezone.utc),
            ))
        return records

    @staticmethod
    def _build_text_chunk(domain: str, seendate: str, title: str) -> str:
        who = domain or "news source"
        when = f" ({seendate})" if seendate else ""
        return f'{who} reported{when}: "{title}".'

    # ── cursor / request building ──────────────────────────────────────────────────

    def build_request_payload(self, cursor: dict | None, page: int = 1) -> dict:
        # page (1-based) selects the probe; the window is a fixed rolling timespan (no forward
        # watermark — that trap silently zeroed USAspending, Phase B). Dedup absorbs repeats.
        probe = _PROBES[(page - 1) % len(_PROBES)]
        self._active_probe = probe
        return {
            "query": f'"{probe.query}"',   # quoted exact phrase
            "mode": "artlist",
            "format": "json",
            "maxrecords": _MAXRECORDS,
            "timespan": _TIMESPAN,
            "sort": "datedesc",
        }

    def next_cursor(self, response, current_page: int) -> dict:
        # Walk every probe once per run, then advance the date watermark.
        if current_page < len(_PROBES):
            return {"page": current_page + 1}
        return {"last_date": date.today().isoformat()}
