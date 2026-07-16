"""Tests for the generic RSS/Atom feed adapter (D104).
All tests run against inline XML fixtures — no network.

Spec: one adapter parses both RSS 2.0 and Atom into normalized `news` records tagged
to each feed's single home desk (D097), title + short snippet + link only (scrape_gray),
HTML stripped, malformed XML tolerated, bounded per feed. The feed registry spans all
three desks; per-feed isolation lives in enrich() (covered by the parse-level tests +
the registry being walked there).
"""
from engine.adapters.feeds import (
    _FEEDS,
    _MAX_ITEMS_PER_FEED,
    FeedsAdapter,
    _Feed,
    parse_feed,
)

_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>Breaking Defense</title>
  <item>
    <title>Army awards <b>hypersonic</b> missile contract</title>
    <link>https://example.com/a</link>
    <guid>https://example.com/a</guid>
    <description>&lt;p&gt;The Army has awarded a large contract for hypersonic development.&lt;/p&gt;</description>
    <pubDate>Mon, 28 Jun 2026 12:00:00 GMT</pubDate>
  </item>
  <item>
    <title>No link item should still parse via guid</title>
    <guid>urn:uuid:123</guid>
  </item>
  <item>
    <description>no title — skipped</description>
    <link>https://example.com/c</link>
  </item>
</channel></rss>"""

_ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>The Register</title>
  <entry>
    <title>New GPU breaks inference records</title>
    <link rel="alternate" href="https://example.com/gpu"/>
    <id>tag:example.com,2026:1</id>
    <summary>A new accelerator posts strong numbers.</summary>
    <updated>2026-06-28T12:00:00Z</updated>
  </entry>
</feed>"""

_DEF_FEED = _Feed("https://x/feed", "Breaking Defense", "defense")
_AI_FEED = _Feed("https://x/atom", "The Register", "ai")


class TestParseFeed:
    def test_rss_parses_items_with_link_or_guid(self):
        recs = parse_feed(_RSS, _DEF_FEED)
        # item 1 (link+guid) and item 2 (guid only) survive; item 3 (no title) is dropped.
        assert len(recs) == 2

    def test_rss_record_shape_and_html_stripped(self):
        rec = parse_feed(_RSS, _DEF_FEED)[0]
        assert rec.source_id == "feeds"
        assert rec.record_type == "news"
        assert rec.desk == ["defense"]
        assert rec.entity_mentions == []
        assert rec.url == "https://example.com/a"
        # HTML tags stripped from the title and snippet
        assert "<b>" not in rec.structured_data["title"]
        assert rec.structured_data["title"] == "Army awards hypersonic missile contract"
        assert "<p>" not in rec.structured_data["snippet"]

    def test_text_chunk_is_outlet_attributed(self):
        rec = parse_feed(_RSS, _DEF_FEED)[0]
        assert rec.text_chunk.startswith('Breaking Defense reported: "Army awards hypersonic')

    def test_atom_uses_href_link_and_id(self):
        rec = parse_feed(_ATOM, _AI_FEED)[0]
        assert rec.url == "https://example.com/gpu"
        assert rec.native_id == "tag:example.com,2026:1"
        assert rec.desk == ["ai"]

    def test_malformed_xml_returns_empty(self):
        assert parse_feed("<not xml", _DEF_FEED) == []
        assert parse_feed("", _DEF_FEED) == []

    def test_items_capped_per_feed(self):
        many = "".join(
            f"<item><title>t{i}</title><link>https://x/{i}</link></item>"
            for i in range(_MAX_ITEMS_PER_FEED + 5)
        )
        xml = f'<rss version="2.0"><channel>{many}</channel></rss>'
        assert len(parse_feed(xml, _DEF_FEED)) == _MAX_ITEMS_PER_FEED


class TestCommerceNoiseFilter:
    # Real 7/5 AI-wire junk (Tom's Hardware) that must be dropped at parse (D122).
    _JUNK = [
        "Save up to 47% on Dell and Alienware gaming PCs and laptops in this July 4th flash sale",
        "Save up to 71% on HP gaming desktops and laptops this July 4",
        "Up to $129 off Secretlab gaming chairs and desks in July 4 sale",
        "Get a premium 27-inch 1440p 240 Hz OLED gaming monitor for only $349 — OLED for the price of IPS",
        "The ultimate 4K RTX 5090 gaming titan plummets $2,580 — huge discount makes the Alienware Area-51 irresistible",
        "Sony crammed an entire PS1 into a DualShock controller that connects to your TV",
        "50-feet-long fiber optic HDMI cable and Steam Controller 2 is enthusiasts' answer to the Steam Machine",
        "AOC U27G4XM 27-inch 4K 160 Hz Dual-Refresh Gaming Monitor Review",
    ]
    # Real compute-supply signal from the same feed that MUST survive.
    _KEEP = [
        "Intel 18A wafer-to-wafer yield issues fixed, report claims — production up to 15,000 wafers/month",
        "Memory price surge begins to cool — AI demand still keeps DRAM and NAND prices climbing through Q3 2026",
        "Inside the history of DRAM price-fixing lawsuits — how HBM allocations could make a difference",
        "SK hynix, Samsung, Micron among semiconductor industry group lobbying against government intervention",
        "Intel reportedly adding two new 22-core SKUs with game-boosting cache to Nova Lake-S lineup",
        "National Grid Ventures invests $1.75bn in gas plant powering 2GW Microsoft data center in Texas",
    ]

    def _item(self, title: str) -> str:
        return f"<item><title>{title}</title><link>https://x/1</link></item>"

    def test_commerce_noise_dropped(self):
        for title in self._JUNK:
            xml = f'<rss version="2.0"><channel>{self._item(title)}</channel></rss>'
            assert parse_feed(xml, _AI_FEED) == [], f"should drop: {title}"

    def test_supply_chain_signal_survives(self):
        for title in self._KEEP:
            xml = f'<rss version="2.0"><channel>{self._item(title)}</channel></rss>'
            assert len(parse_feed(xml, _AI_FEED)) == 1, f"should keep: {title}"


class TestFeedRegistry:
    def test_registry_spans_all_three_desks(self):
        assert {f.desk for f in _FEEDS} == {"defense", "ai", "energy"}

    def test_every_feed_has_url_and_name(self):
        for f in _FEEDS:
            assert f.url.startswith("http") and f.name

    def test_no_duplicate_feed_urls(self):
        # Registry hygiene as the list grows (breadth expansion, D-feeds): a dup URL just
        # wastes a fetch and double-counts an outlet.
        urls = [f.url for f in _FEEDS]
        assert len(urls) == len(set(urls))

    def test_d145_census_additions_present_and_routed(self):
        # D145: outlets a GDELT source census surfaced as missing, then RSS-verified. Home desk
        # pinned so a registry edit can't silently re-route them.
        by_name = {f.name: f.desk for f in _FEEDS}
        assert by_name["Military Times"] == "defense"
        assert by_name["OilPrice"] == "energy"
        assert by_name["Blocks & Files"] == "ai"

    def test_base_url_tracks_active_canary_feed(self):
        adapter = FeedsAdapter()
        adapter.build_request_payload(cursor=None, page=1)
        assert adapter.base_url == _FEEDS[0].url
        assert adapter.max_pages == 1
