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
    def test_page_selects_probe_and_quotes_phrase(self):
        adapter = GDELTAdapter()
        payload = adapter.build_request_payload(cursor=None, page=1)
        assert payload["mode"] == "artlist"
        assert payload["format"] == "json"
        assert payload["maxrecords"] == _MAXRECORDS
        assert payload["query"] == f'"{_PROBES[0].query}"'

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
        ):
            assert topic in queries, f"missing GDELT coverage for: {topic}"

    def test_next_cursor_walks_then_watermarks(self):
        adapter = GDELTAdapter()
        assert adapter.next_cursor({}, current_page=1) == {"page": 2}
        last = adapter.next_cursor({}, current_page=len(_PROBES))
        assert "last_date" in last

    def test_max_pages_is_probe_count(self):
        assert GDELTAdapter().max_pages == len(_PROBES)
