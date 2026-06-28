"""Generic RSS/Atom feed adapter — the scale lever for breadth (D104).

The binding constraint on HPI is coverage breadth, and most of the universe outside
federal structured data (trade press, think tanks, company IR, associations — see
`docs/SOURCE_LANDSCAPE.md` categories C–G) is published as **RSS/Atom feeds**. Rather
than a bespoke adapter per outlet, this ONE adapter is driven by a registry of feeds
(`_FEEDS`), each carrying its home desk. Onboarding a new outlet is one line, not a build.

Made admissible by the epistemic flip (D098/D099): a configured, named outlet is
**attributed third-party reporting** → the `reported` confidence tier (vs GDELT's raw,
un-vetted global firehose, which is `speculative`). `source_id="feeds"` so the whole
class maps to `reported` in `epistemics` and a modest materiality weight; `license_class`
is `scrape_gray` — we store/cite the **title + link + a short snippet**, never full text.

Per-feed `license_class`/`source_reliability` overrides (e.g. a gov feed → public_domain,
a vetted outlet promoted, a weak one demoted to speculative) are the documented follow-up;
today every feed is handled uniformly and conservatively (scrape_gray / reported).

**Robustness:** feeds die. The runner fetches the first feed (the canary) on page 1; the
rest are fetched in ``enrich`` with **per-feed try/except**, so one dead outlet can never
abort the others. A feed that 404s is logged and skipped, not fatal.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import structlog

from .base import NormalizedRecord

log = structlog.get_logger()

_SOURCE_ID = "feeds"
_TITLE_CHARS = 300
_SUMMARY_CHARS = 300       # scrape_gray: a SHORT snippet only, never the full article
_MAX_ITEMS_PER_FEED = 12   # most-recent items per feed; bounds volume
_USER_AGENT = "HardPowerIntelligence/1.0 (hardpowerintelligence@gmail.com)"
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class _Feed:
    url: str
    name: str        # outlet display name (the attribution shown to the reader)
    desk: str        # single home desk (D097 demarcation)


# Curated feed registry (operator source review, 2026-06-28; see SOURCE_LANDSCAPE.md §E/G).
# Position 0 is the runner-fetched "canary" — keep it a stable, high-availability feed.
# URLs are best-known and need live validation; a bad URL fails only its own feed (isolated).
_FEEDS: tuple[_Feed, ...] = (
    # ── Defense trade press ──
    _Feed("https://breakingdefense.com/feed/", "Breaking Defense", "defense"),
    _Feed("https://defensescoop.com/feed/", "DefenseScoop", "defense"),
    _Feed("https://www.defenseone.com/rss/all/", "Defense One", "defense"),
    _Feed("https://www.twz.com/feed", "The War Zone", "defense"),
    _Feed("https://www.navalnews.com/feed/", "Naval News", "defense"),
    _Feed("https://spacenews.com/feed/", "SpaceNews", "defense"),
    # ── AI / compute trade press ──
    _Feed("https://www.datacenterdynamics.com/en/rss/", "Data Center Dynamics", "ai"),
    _Feed("https://spectrum.ieee.org/feeds/feed.rss", "IEEE Spectrum", "ai"),
    _Feed("https://www.hpcwire.com/feed/", "HPCwire", "ai"),
    _Feed("https://www.theregister.com/headlines.atom", "The Register", "ai"),
    _Feed("https://www.tomshardware.com/feeds/all", "Tom's Hardware", "ai"),
    _Feed("https://semianalysis.com/feed/", "SemiAnalysis", "ai"),
    # ── Energy trade press ──
    _Feed("https://www.utilitydive.com/feeds/news/", "Utility Dive", "energy"),
    _Feed("https://www.world-nuclear-news.org/rss", "World Nuclear News", "energy"),
    _Feed("https://www.powermag.com/feed/", "POWER Magazine", "energy"),
    _Feed("https://www.pv-magazine.com/feed/", "pv magazine", "energy"),
    # ── Think tanks / research (reported) ──
    # Live-validated 2026-06-28: CSIS /rss.xml ✓ (the /analysis/feed path was 404);
    # RAND + Canary Media bot-blocked (403), dropped — RAND replaced by War on the Rocks.
    _Feed("https://www.csis.org/rss.xml", "CSIS", "defense"),
    _Feed("https://warontherocks.com/feed/", "War on the Rocks", "defense"),
    _Feed("https://rmi.org/feed/", "RMI", "energy"),
    _Feed("https://cset.georgetown.edu/feed/", "CSET (Georgetown)", "ai"),
)


def _strip(text: str | None) -> str:
    return " ".join(_TAG_RE.sub(" ", text or "").split())


def _first_link(item) -> str:
    """RSS <link> is text; Atom <link> carries the URL in href (prefer rel=alternate)."""
    text_link = ""
    href_alt = href_any = ""
    for child in item:
        if _local(child.tag) != "link":
            continue
        if (child.text or "").strip():
            text_link = child.text.strip()
        href = child.get("href", "")
        if href:
            href_any = href_any or href
            if child.get("rel", "alternate") == "alternate":
                href_alt = href_alt or href
    return text_link or href_alt or href_any


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_feed(xml_text: str, feed: _Feed) -> list[NormalizedRecord]:
    """Parse one RSS/Atom feed body into normalized ``news`` records (pure, no network)."""
    try:
        root = ET.fromstring(xml_text.encode() if isinstance(xml_text, str) else xml_text)
    except ET.ParseError:
        return []

    records: list[NormalizedRecord] = []
    items = [e for e in root.iter() if _local(e.tag) in ("item", "entry")]
    for item in items[:_MAX_ITEMS_PER_FEED]:
        title = guid = summary = published = ""
        for child in item:
            t = _local(child.tag)
            if t == "title":
                title = _strip("".join(child.itertext()))
            elif t in ("guid", "id"):
                guid = _strip(child.text)
            elif t in ("description", "summary", "content") and not summary:
                summary = _strip("".join(child.itertext()))
            elif t in ("pubdate", "published", "updated", "date") and not published:
                published = _strip(child.text)
        link = _first_link(item)
        title = title[:_TITLE_CHARS]
        if not title or not (link or guid):
            continue
        native = guid or link
        snippet = summary[:_SUMMARY_CHARS]

        records.append(NormalizedRecord(
            source_id=_SOURCE_ID,
            record_type="news",
            desk=[feed.desk],
            entity_mentions=[],        # NER deferred (same as GDELT, D101)
            structured_data={
                "title": title, "outlet": feed.name, "url": link,
                "published": published, "snippet": snippet,
            },
            # scrape_gray: outlet attribution + title + a SHORT snippet + link. Never full text.
            text_chunk=_build_text_chunk(feed.name, title, snippet),
            content_hash=hashlib.sha256(f"{native}\n{title}".encode()).hexdigest(),
            native_id=native,
            url=link,
        ))
    return records


def _build_text_chunk(outlet: str, title: str, snippet: str) -> str:
    base = f'{outlet} reported: "{title}".'
    return f"{base} {snippet}" if snippet else base


class FeedsAdapter:
    source_id: str = _SOURCE_ID
    http_method: str = "GET"
    response_format: str = "text"

    def __init__(self) -> None:
        self._active: _Feed = _FEEDS[0]

    @property
    def base_url(self) -> str:
        # The runner reads base_url AFTER build_request_payload, so this returns the
        # canary feed (page 1). The remaining feeds are fetched in enrich().
        return self._active.url

    @property
    def headers(self) -> dict:
        return {"User-Agent": _USER_AGENT}

    @property
    def max_pages(self) -> int:
        return 1   # page 1 = canary; enrich() walks the rest, isolated

    def build_request_payload(self, cursor: dict | None, page: int = 1) -> dict:
        self._active = _FEEDS[0]
        return {}   # the full feed URL is base_url; no query params

    def parse(self, response: str) -> list[NormalizedRecord]:
        # Page-1 canary feed (fetched by the runner).
        return parse_feed(response if isinstance(response, str) else "", self._active)

    async def enrich(self, records: list[NormalizedRecord], fetcher) -> list[NormalizedRecord]:
        """Fetch every NON-canary feed with per-feed isolation and append its records.

        A single dead/404 feed is logged and skipped — never fatal to the others
        (the runner's try/except is per-source, so without this one bad URL would
        abort the whole feeds run)."""
        out = list(records)
        for feed in _FEEDS[1:]:
            try:
                body = await fetcher.fetch_json(
                    "GET", feed.url, headers=self.headers, response_format="text",
                )
                out.extend(parse_feed(body if isinstance(body, str) else "", feed))
            except Exception as exc:  # noqa: BLE001 — one dead feed must not abort the rest
                log.warning("feed_fetch_skipped", feed=feed.name, url=feed.url, error=str(exc))
        return out

    def next_cursor(self, response, current_page: int) -> dict:
        # Single logical page (canary + enrich). Nothing to paginate.
        return {}
