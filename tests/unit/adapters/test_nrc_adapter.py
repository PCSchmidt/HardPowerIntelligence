"""Tests for the NRC (Federal Register API) adapter — the Energy desk's regulatory leg (D095).
All tests run against an inline golden fixture — no network calls."""
import json
from datetime import date, timedelta

import pytest

from engine.adapters.nrc import NRCAdapter, _LOOKBACK_DAYS, _PROBES, _AGENCY_SLUG


@pytest.fixture
def nrc_response() -> dict:
    # Shape mirrors the live Federal Register documents.json response (confirmed 2026-06-20).
    return {
        "count": 2,
        "total_pages": 1,
        "results": [
            {
                "document_number": "2026-12515",
                "title": "Oklo Power, LLC; Aurora Powerhouse Combined License Application",
                "type": "Notice",
                "abstract": "The U.S. Nuclear Regulatory Commission is considering a combined "
                            "license application for an advanced small modular reactor.",
                "html_url": "https://www.federalregister.gov/documents/2026/06/22/2026-12515/oklo",
                "publication_date": "2026-06-22",
                "agencies": [
                    {"raw_name": "NUCLEAR REGULATORY COMMISSION",
                     "name": "Nuclear Regulatory Commission",
                     "slug": "nuclear-regulatory-commission"},
                ],
            },
            {
                "document_number": "2026-12777",
                "title": "High-Assay Low-Enriched Uranium Fuel Qualification Rulemaking",
                "type": "Proposed Rule",
                "abstract": "The NRC proposes to amend its regulations to support HALEU fuel.",
                "html_url": "https://www.federalregister.gov/documents/2026/06/23/2026-12777/haleu",
                "publication_date": "2026-06-23",
                "agencies": [
                    {"name": "Nuclear Regulatory Commission",
                     "slug": "nuclear-regulatory-commission"},
                ],
            },
        ],
    }


class TestParse:
    def test_returns_record_per_result(self, nrc_response):
        records = NRCAdapter().parse(nrc_response)
        assert len(records) == 2

    def test_native_id_is_document_number(self, nrc_response):
        records = NRCAdapter().parse(nrc_response)
        assert records[0].native_id == "2026-12515"

    def test_source_id_and_record_type(self, nrc_response):
        records = NRCAdapter().parse(nrc_response)
        for r in records:
            assert r.source_id == "nrc"
            assert r.record_type == "regulatory_document"

    def test_default_probe_tags_energy(self, nrc_response):
        records = NRCAdapter().parse(nrc_response)
        for r in records:
            assert r.desk == ["energy"]

    def test_structured_data_fields(self, nrc_response):
        records = NRCAdapter().parse(nrc_response)
        sd = records[0].structured_data
        assert sd["document_number"] == "2026-12515"
        assert sd["doc_type"] == "Notice"
        assert sd["publication_date"] == "2026-06-22"
        assert sd["agency"] == "Nuclear Regulatory Commission"
        assert "small modular reactor" in sd["abstract"]

    def test_no_amount_usd(self, nrc_response):
        # A regulatory document has no dollar figure — it scores on authority+novelty, not magnitude.
        records = NRCAdapter().parse(nrc_response)
        assert "amount_usd" not in records[0].structured_data

    def test_links_allowlisted_company_via_ticker(self, nrc_response):
        # Precision-first linking (D096): a named public nuclear company yields a ticker-bearing
        # mention the linker resolves via the exact-identifier path. The Oklo notice → OKLO.
        records = NRCAdapter().parse(nrc_response)
        oklo = records[0]
        assert len(oklo.entity_mentions) == 1
        m = oklo.entity_mentions[0]
        assert m["mention"] == "Oklo"
        assert m["ticker"] == "OKLO"
        assert m["entity_type"] == "company"

    def test_no_mention_when_no_allowlisted_company_named(self, nrc_response):
        # The HALEU rulemaking names no allowlisted company → no mention (no false link).
        records = NRCAdapter().parse(nrc_response)
        assert records[1].entity_mentions == []

    def test_mention_match_is_word_bounded(self):
        # "Vistra" matches; an incidental substring must not.
        adapter = NRCAdapter()
        resp = {"results": [{
            "document_number": "x", "title": "Vistra Comanche Peak License Renewal",
            "type": "Notice", "abstract": "", "html_url": "", "publication_date": "2026-06-20",
            "agencies": [{"name": "Nuclear Regulatory Commission"}],
        }]}
        tickers = {m["ticker"] for m in adapter.parse(resp)[0].entity_mentions}
        assert tickers == {"VST"}

    def test_text_chunk_reads_as_policy(self, nrc_response):
        chunk = NRCAdapter().parse(nrc_response)[0].text_chunk
        assert "Nuclear Regulatory Commission" in chunk
        assert "Notice" in chunk
        assert "Combined License" in chunk  # from the title
        assert "Summary:" in chunk

    def test_url_falls_back_when_html_url_missing(self, nrc_response):
        resp = json.loads(json.dumps(nrc_response))
        del resp["results"][0]["html_url"]
        records = NRCAdapter().parse(resp)
        assert records[0].url == "https://www.federalregister.gov/d/2026-12515"

    def test_missing_abstract_does_not_raise(self, nrc_response):
        resp = json.loads(json.dumps(nrc_response))
        resp["results"][0]["abstract"] = None
        records = NRCAdapter().parse(resp)
        assert records[0].structured_data["abstract"] == ""

    def test_skips_rows_without_document_number_or_title(self, nrc_response):
        resp = json.loads(json.dumps(nrc_response))
        resp["results"][0]["document_number"] = ""
        resp["results"][1]["title"] = ""
        assert NRCAdapter().parse(resp) == []

    def test_empty_results(self):
        assert NRCAdapter().parse({"results": []}) == []


class TestContentHash:
    def test_deterministic_and_sha256_hex(self, nrc_response):
        records = NRCAdapter().parse(nrc_response)
        again = NRCAdapter().parse(nrc_response)
        assert records[0].content_hash == again[0].content_hash
        assert len(records[0].content_hash) == 64
        assert all(c in "0123456789abcdef" for c in records[0].content_hash)

    def test_hash_excludes_probe_term_so_cross_probe_dedups(self, nrc_response):
        # The same document surfaced by two different probe terms must hash identically.
        a = NRCAdapter()
        a.build_request_payload(None, page=1)        # "small modular reactor"
        h1 = a.parse(nrc_response)[0].content_hash
        b = NRCAdapter()
        b.build_request_payload(None, page=3)        # "high-assay low-enriched uranium"
        h2 = b.parse(nrc_response)[0].content_hash
        assert h1 == h2

    def test_hash_changes_on_title_change(self, nrc_response):
        original = NRCAdapter().parse(nrc_response)[0].content_hash
        resp = json.loads(json.dumps(nrc_response))
        resp["results"][0]["title"] = "Different Title Entirely"
        changed = NRCAdapter().parse(resp)[0].content_hash
        assert original != changed


class TestProbes:
    def test_all_probes_are_energy_only(self):
        # NRC is the Energy desk's regulatory leg; every probe is energy-home (D095).
        # Count grows as the nuclear front widens (microreactor/TRISO added D102).
        assert NRCAdapter().probe_count == len(_PROBES)
        assert _PROBES  # non-empty
        for probe in _PROBES:
            assert probe.desks == ("energy",)

    def test_probe_terms_are_on_thesis(self):
        terms = {p.term for p in _PROBES}
        assert "small modular reactor" in terms
        assert "high-assay low-enriched uranium" in terms
        assert "combined license" in terms

    def test_max_pages_equals_probe_count(self):
        assert NRCAdapter().max_pages == NRCAdapter().probe_count


class TestRequestBuilding:
    def test_payload_filters_to_nrc_agency_and_probe_term(self):
        adapter = NRCAdapter()
        payload = adapter.build_request_payload(None, page=1)
        assert payload["conditions[agencies][]"] == _AGENCY_SLUG
        assert payload["conditions[term]"] == "small modular reactor"
        assert payload["order"] == "newest"

    def test_page_selects_probe(self):
        adapter = NRCAdapter()
        assert adapter.build_request_payload(None, page=3)["conditions[term]"] \
            == "high-assay low-enriched uranium"

    def test_window_is_fixed_rolling_lookback_ignoring_cursor(self):
        # Mirror the USAspending lesson: a forward watermark is the trap — always a fixed lookback.
        adapter = NRCAdapter()
        payload = adapter.build_request_payload({"last_date": "2026-01-01"}, page=1)
        expected = (date.today() - timedelta(days=_LOOKBACK_DAYS)).isoformat()
        assert payload["conditions[publication_date][gte]"] == expected
        assert payload["conditions[publication_date][gte]"] != "2026-01-01"

    def test_requests_explicit_fields(self):
        fields = NRCAdapter().build_request_payload(None, page=1)["fields[]"]
        for f in ("document_number", "title", "type", "abstract", "publication_date"):
            assert f in fields


class TestCursor:
    def test_next_cursor_walks_probes(self, nrc_response):
        assert NRCAdapter().next_cursor(nrc_response, current_page=1) == {"page": 2}

    def test_next_cursor_terminal_after_last_probe(self, nrc_response):
        adapter = NRCAdapter()
        cursor = adapter.next_cursor(nrc_response, current_page=adapter.probe_count)
        assert "page" not in cursor
        assert "last_date" in cursor
