"""Tests for the GDELT-as-story adapter — worldwide news radar (D101).
All tests run against an inline golden fixture — no network calls.

Spec: GDELT articles parse into normalized 'news' records tagged to their probe's single
home desk (D097), title + link only (scrape_gray), English-only, no entity links yet; the
probe walk and dedup-stable hashing mirror the other probe adapters.
"""
import pytest

from engine.adapters.gdelt import GDELTAdapter, _MAXRECORDS, _PROBES, _TITLE_CHARS


@pytest.fixture
def gdelt_response() -> dict:
    # Shape mirrors the live GDELT DOC 2.0 ArtList JSON response.
    return {
        "articles": [
            {
                "url": "https://example-defense.com/hypersonic-test",
                "title": "Pentagon confirms successful hypersonic missile test",
                "domain": "example-defense.com",
                "seendate": "20260628T120000Z",
                "language": "English",
                "sourcecountry": "United States",
            },
            {
                "url": "https://exemplo.br/missil",
                "title": "Teste de míssil hipersônico",
                "domain": "exemplo.br",
                "seendate": "20260628T130000Z",
                "language": "Portuguese",
                "sourcecountry": "Brazil",
            },
            {
                "url": "",
                "title": "No URL — should be skipped",
                "domain": "broken.com",
                "seendate": "20260628T140000Z",
                "language": "English",
                "sourcecountry": "United States",
            },
        ],
    }


class TestParse:
    def test_keeps_english_with_url_skips_others(self, gdelt_response):
        # 1 of 3 survives: the Portuguese article and the URL-less article are dropped.
        records = GDELTAdapter().parse(gdelt_response)
        assert len(records) == 1
        assert records[0].native_id == "https://example-defense.com/hypersonic-test"

    def test_record_shape(self, gdelt_response):
        rec = GDELTAdapter().parse(gdelt_response)[0]
        assert rec.source_id == "gdelt"
        assert rec.record_type == "news"
        assert rec.entity_mentions == []          # no NER yet
        assert rec.url == "https://example-defense.com/hypersonic-test"

    def test_text_chunk_is_attributed_title_only(self, gdelt_response):
        rec = GDELTAdapter().parse(gdelt_response)[0]
        # scrape_gray: domain attribution + the title, link only — no body text.
        assert rec.text_chunk == (
            'example-defense.com reported (20260628T120000Z): '
            '"Pentagon confirms successful hypersonic missile test".'
        )

    def test_desk_is_the_active_probe_home_desk(self, gdelt_response):
        adapter = GDELTAdapter()
        adapter.build_request_payload(cursor=None, page=1)   # probe 0 → defense
        rec = adapter.parse(gdelt_response)[0]
        assert rec.desk == ["defense"]
        assert len(rec.desk) == 1                  # exactly one home desk (D097)

    def test_title_truncated(self):
        long_title = "x" * (_TITLE_CHARS + 50)
        resp = {"articles": [{"url": "https://a.com/1", "title": long_title,
                              "domain": "a.com", "language": "English"}]}
        rec = GDELTAdapter().parse(resp)[0]
        assert len(rec.structured_data["title"]) == _TITLE_CHARS

    def test_hash_ignores_probe_query_so_cross_probe_dedups(self, gdelt_response):
        # Same article surfaced under two different probes → identical content_hash.
        a = GDELTAdapter()
        a.build_request_payload(cursor=None, page=1)
        rec_a = a.parse(gdelt_response)[0]
        b = GDELTAdapter()
        b.build_request_payload(cursor=None, page=2)
        rec_b = b.parse(gdelt_response)[0]
        assert rec_a.content_hash == rec_b.content_hash


class TestRequestBuilding:
    def test_page_selects_consolidated_or_query(self):
        from engine.adapters.gdelt import _QUERIES
        adapter = GDELTAdapter()
        payload = adapter.build_request_payload(cursor=None, page=1)
        assert payload["mode"] == "artlist"
        assert payload["format"] == "json"
        assert payload["maxrecords"] == _MAXRECORDS
        # Query is the pre-combined OR group for the first desk, not a single phrase (D109).
        assert payload["query"] == _QUERIES[0].query
        assert payload["query"].startswith("(") and payload["query"].endswith(")")
        # The first probe's phrase is one of the OR clauses in the first group.
        assert f'"{_PROBES[0].query}"' in payload["query"]

    def test_probes_span_all_three_desks(self):
        desks = {p.desk for p in _PROBES}
        assert desks == {"defense", "ai", "energy"}

    def test_cutting_edge_topics_are_covered(self):
        # Guard against silently dropping the cutting-edge fronts (operator review, D102).
        queries = {p.query for p in _PROBES}
        for topic in (
            "collaborative combat aircraft",   # defense autonomy
            "high-power microwave weapon",     # directed energy
            "quantum sensing navigation",      # alternative PNT
            "Nvidia Blackwell",                # AI accelerators
            "high bandwidth memory",           # AI memory
            "silicon photonics",               # AI photonics
            "nuclear microreactor",            # energy micro-nuclear
            "enhanced geothermal",             # energy geothermal
            "iron-air battery",                # energy LDES
            "space-based solar power",         # SBSP convergence
            "orbital data center",             # compute-in-space
            "contested logistics",             # defense sustainment
            "Ultra Ethernet AI networking",    # AI networking fabric
            "optical circuit switching",       # AI networking fabric
            "hydrokinetic turbine",            # energy next-gen hydro
            "grid transformer shortage",       # grid-component crunch
        ):
            assert topic in queries, f"missing GDELT coverage for: {topic}"

    def test_next_cursor_walks_then_watermarks(self):
        from engine.adapters.gdelt import _QUERIES
        adapter = GDELTAdapter()
        assert adapter.next_cursor({}, current_page=1) == {"page": 2}
        last = adapter.next_cursor({}, current_page=len(_QUERIES))
        assert "last_date" in last


class TestConsolidatedQueries:
    """D109: the ~50 single-phrase probes are OR-combined into a few bounded per-desk queries
    so GDELT (which rate-limits ~1 req/5s) isn't stormed into HTTP 429."""

    def test_far_fewer_queries_than_probes(self):
        from engine.adapters.gdelt import _QUERIES
        assert len(_QUERIES) < len(_PROBES)

    def test_every_probe_phrase_is_covered(self):
        # No coverage lost in consolidation: every probe phrase appears in some query.
        from engine.adapters.gdelt import _QUERIES
        haystack = " ".join(q.query for q in _QUERIES)
        for p in _PROBES:
            assert f'"{p.query}"' in haystack, f"dropped phrase: {p.query}"

    def test_each_query_is_single_desk_and_or_combined(self):
        from engine.adapters.gdelt import _QUERIES, _QUERY_GROUP_SIZE
        for q in _QUERIES:
            assert q.desk in {"defense", "ai", "energy"}
            assert q.query.startswith("(") and q.query.endswith(")")
            # Bounded to the proven-safe OR-clause envelope.
            assert q.query.count('"') // 2 <= _QUERY_GROUP_SIZE

    def test_a_query_only_mixes_one_desks_phrases(self):
        # Every phrase OR'd into a query shares that query's home desk (preserves D097).
        from engine.adapters.gdelt import _QUERIES
        phrase_desk = {p.query: p.desk for p in _PROBES}
        for q in _QUERIES:
            for phrase, desk in phrase_desk.items():
                if f'"{phrase}"' in q.query:
                    assert desk == q.desk

    def test_throttle_hint_present(self):
        # The runner spaces GDELT requests by this interval to stay under the rate limit.
        assert GDELTAdapter().min_request_interval >= 5.0

    def test_sends_descriptive_user_agent(self):
        # GDELT 429s anonymous/default library agents; we must send a real UA (D110).
        ua = GDELTAdapter().headers["User-Agent"]
        assert ua and "httpx" not in ua.lower() and "python" not in ua.lower()

    def test_max_pages_is_query_count(self):
        # One API call per CONSOLIDATED query now, not per probe (D109).
        from engine.adapters.gdelt import _QUERIES
        assert GDELTAdapter().max_pages == len(_QUERIES)
