"""Tests for the SAM.gov opportunities adapter (D105) — Phase 2 federal veins.
All tests run against an inline golden fixture — no network.

Spec: SAM.gov opportunity notices parse into confirmed-tier `award` records tagged to
their probe's single home desk (D097); native_id = noticeId; title + agency + link
(public_domain primary record); the probe walk + dedup-stable hashing mirror the other
probe adapters.
"""
import pytest

from engine.adapters.sam_gov import SAMGovAdapter, _LIMIT, _PROBES


@pytest.fixture
def sam_response() -> dict:
    # Shape mirrors the live SAM.gov Opportunities v2 API response.
    return {
        "totalRecords": 2,
        "opportunitiesData": [
            {
                "noticeId": "abc123",
                "title": "Hypersonic Glide Body Production Capacity",
                "fullParentPathName": "DEPT OF DEFENSE.DEPT OF THE ARMY",
                "type": "Solicitation",
                "postedDate": "2026-06-25",
                "solicitationNumber": "W912-26-R-0001",
                "naicsCode": "336414",
                "uiLink": "https://sam.gov/opp/abc123/view",
            },
            {
                "noticeId": "def456",
                "title": "",  # no title — skipped
                "fullParentPathName": "DEPT OF DEFENSE",
                "type": "Presolicitation",
                "postedDate": "2026-06-24",
                "uiLink": "https://sam.gov/opp/def456/view",
            },
        ],
    }


class TestParse:
    def test_skips_titleless_notice(self, sam_response):
        recs = SAMGovAdapter().parse(sam_response)
        assert len(recs) == 1

    def test_record_shape(self, sam_response):
        rec = SAMGovAdapter().parse(sam_response)[0]
        assert rec.source_id == "sam_gov"
        assert rec.record_type == "award"
        assert rec.native_id == "abc123"
        assert rec.url == "https://sam.gov/opp/abc123/view"
        assert rec.desk == ["defense"]            # probe 0 is defense
        assert "Hypersonic" in rec.text_chunk and "ARMY" in rec.text_chunk.upper()

    def test_hash_ignores_probe_query(self, sam_response):
        a = SAMGovAdapter(); a.build_request_payload(None, page=1)
        b = SAMGovAdapter(); b.build_request_payload(None, page=2)
        assert a.parse(sam_response)[0].content_hash == b.parse(sam_response)[0].content_hash


class TestRequestBuilding:
    def test_page_selects_probe_and_sets_required_params(self):
        adapter = SAMGovAdapter()
        payload = adapter.build_request_payload(cursor=None, page=1)
        # SAM Opportunities v2 has no free-text "q" param — keyword search is the `title`
        # field (D110 fix); the probe keyword is mapped there.
        assert payload["title"] == _PROBES[0].q
        assert payload["limit"] == _LIMIT
        assert adapter.base_url.endswith("/prod/opportunities/v2/search")
        # SAM requires a posted-date range in MM/DD/YYYY
        assert "/" in payload["postedFrom"] and "/" in payload["postedTo"]
        assert "api_key" in payload

    def test_probes_span_all_three_desks(self):
        assert {p.desk for p in _PROBES} == {"defense", "ai", "energy"}

    def test_next_cursor_walks_then_watermarks(self):
        adapter = SAMGovAdapter()
        assert adapter.next_cursor({}, 1) == {"page": 2}
        assert "last_date" in adapter.next_cursor({}, len(_PROBES))
