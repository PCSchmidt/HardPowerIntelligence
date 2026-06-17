"""Tests for the SEC EDGAR full-text search adapter (D055 §10, D060).
Fixture mirrors a real EFTS response — no network calls.
"""
import pytest
from engine.adapters.edgar import EDGARFullTextAdapter


@pytest.fixture
def efts_response() -> dict:
    return {
        "hits": {
            "total": {"value": 2, "relation": "eq"},
            "hits": [
                {
                    "_id": "0001822966-26-000052:a2026-05x07xnuscaleq1202.htm",
                    "_source": {
                        "ciks": ["0001822966"],
                        "display_names": ["NUSCALE POWER Corp  (SMR)  (CIK 0001822966)"],
                        "file_date": "2026-05-07",
                        "form": "8-K",
                        "root_forms": ["8-K"],
                        "adsh": "0001822966-26-000052",
                        "items": ["7.01", "9.01"],
                        "sics": ["4911"],
                    },
                },
                {
                    "_id": "0001628280-26-033648:exhibit991.htm",
                    "_source": {
                        "ciks": ["0002011286"],
                        "display_names": ["Amentum Holdings, Inc.  (AMTM)  (CIK 0002011286)"],
                        "file_date": "2026-05-11",
                        "form": "8-K",
                        "adsh": "0001628280-26-033648",
                        "items": ["2.02"],
                        "sics": ["8711"],
                    },
                },
            ],
        }
    }


class TestParse:
    def test_record_count(self, efts_response):
        records = EDGARFullTextAdapter().parse(efts_response)
        assert len(records) == 2

    def test_source_and_type(self, efts_response):
        records = EDGARFullTextAdapter().parse(efts_response)
        for r in records:
            assert r.source_id == "edgar"
            assert r.record_type == "filing"

    def test_native_id_is_accession_doc(self, efts_response):
        records = EDGARFullTextAdapter().parse(efts_response)
        assert records[0].native_id == "0001822966-26-000052:a2026-05x07xnuscaleq1202.htm"

    def test_structured_data(self, efts_response):
        sd = EDGARFullTextAdapter().parse(efts_response)[0].structured_data
        assert sd["accession"] == "0001822966-26-000052"
        assert sd["cik"] == "0001822966"
        assert sd["company_name"] == "NUSCALE POWER Corp"
        assert sd["ticker"] == "SMR"
        assert sd["form"] == "8-K"

    def test_entity_mention_carries_ticker_and_cik(self, efts_response):
        m = EDGARFullTextAdapter().parse(efts_response)[0].entity_mentions[0]
        assert m["mention"] == "NUSCALE POWER Corp"
        assert m["ticker"] == "SMR"
        assert m["cik"] == "0001822966"

    def test_url_points_to_archives(self, efts_response):
        url = EDGARFullTextAdapter().parse(efts_response)[0].url
        # leading zeros stripped from CIK; accession de-dashed
        assert "/Archives/edgar/data/1822966/000182296626000052/" in url

    def test_text_chunk_is_factual_metadata(self, efts_response):
        chunk = EDGARFullTextAdapter().parse(efts_response)[0].text_chunk
        assert "NUSCALE POWER Corp" in chunk
        assert "8-K" in chunk
        assert "small modular reactor" in chunk  # default probe theme

    def test_empty_hits(self):
        assert EDGARFullTextAdapter().parse({"hits": {"hits": []}}) == []

    def test_display_name_without_ticker(self):
        resp = {"hits": {"hits": [{
            "_id": "x:y.htm",
            "_source": {"display_names": ["Privateco LLC  (CIK 0000999)"],
                        "adsh": "x", "form": "8-K", "file_date": "2026-06-01"},
        }]}}
        sd = EDGARFullTextAdapter().parse(resp)[0].structured_data
        assert sd["company_name"] == "Privateco LLC"
        assert sd["ticker"] is None


class TestContentHash:
    def test_deterministic_and_hex(self, efts_response):
        a = EDGARFullTextAdapter().parse(efts_response)
        b = EDGARFullTextAdapter().parse(efts_response)
        assert a[0].content_hash == b[0].content_hash
        assert len(a[0].content_hash) == 64


class TestProbesAndDesks:
    def test_default_probe_is_smr_energy_ai(self, efts_response):
        # Without build_request_payload, parse uses the first probe (SMR → energy, ai).
        records = EDGARFullTextAdapter().parse(efts_response)
        assert set(records[0].desk) == {"energy", "ai"}

    def test_build_sets_probe_and_parse_tags_desks(self, efts_response):
        adapter = EDGARFullTextAdapter()
        # page 8 = "rare earth" probe → all three desks (trilateral chokepoint)
        adapter.build_request_payload(cursor=None, page=8)
        records = adapter.parse(efts_response)
        assert set(records[0].desk) == {"defense", "ai", "energy"}

    def test_build_payload_shape_and_probe_cycling(self):
        adapter = EDGARFullTextAdapter()
        p1 = adapter.build_request_payload(cursor=None, page=1)
        assert p1["q"] == '"small modular reactor"'
        assert p1["forms"] == "8-K"
        assert "startdt" in p1 and "enddt" in p1
        p2 = adapter.build_request_payload(cursor=None, page=2)
        assert p2["q"] == '"high-assay low-enriched uranium"'

    def test_build_payload_uses_cursor_date(self):
        adapter = EDGARFullTextAdapter()
        p = adapter.build_request_payload(cursor={"last_date": "2026-06-01"}, page=1)
        assert p["startdt"] == "2026-06-01"

    def test_next_cursor_walks_probes_then_advances_date(self):
        adapter = EDGARFullTextAdapter()
        assert adapter.next_cursor({}, current_page=1) == {"page": 2}
        # last probe → terminal date cursor
        terminal = adapter.next_cursor({}, current_page=adapter.probe_count)
        assert "last_date" in terminal

    def test_headers_include_user_agent(self):
        assert "User-Agent" in EDGARFullTextAdapter().headers


class TestWidenedProbes:
    """The widened probe set (D077) — breadth without breaking pinned positions."""

    def test_probe_set_widened(self):
        # Was 8; widening must materially increase coverage.
        assert EDGARFullTextAdapter().probe_count >= 30

    def test_max_pages_matches_probe_count(self):
        # The runner reads adapter.max_pages so the global cap doesn't truncate probes.
        adapter = EDGARFullTextAdapter()
        assert adapter.max_pages == adapter.probe_count

    def test_first_eight_probes_unchanged(self):
        adapter = EDGARFullTextAdapter()
        expected = [
            '"small modular reactor"',
            '"high-assay low-enriched uranium"',
            '"hyperscale data center"',
            '"directed energy weapon"',
            '"counter-unmanned aircraft"',
            '"hypersonic"',
            '"autonomous weapon"',
            '"rare earth"',
        ]
        for page, q in enumerate(expected, start=1):
            assert adapter.build_request_payload(cursor=None, page=page)["q"] == q

    def test_every_desk_has_coverage(self):
        from engine.adapters.edgar import _PROBES
        covered = {d for p in _PROBES for d in p.desks}
        assert covered == {"defense", "ai", "energy"}

    def test_added_probes_present(self):
        from engine.adapters.edgar import _PROBES
        queries = {p.query for p in _PROBES}
        # spot-check representative new probes across desks + the trilateral core
        for q in ("grid-scale storage", "munitions production",
                  "large language model", "gallium"):
            assert q in queries
