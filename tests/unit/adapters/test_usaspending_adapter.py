"""
Tests for the USAspending adapter.
All tests run against golden fixtures — no network calls.
Gate 4 acceptance: these tests must pass.
"""

import json

from engine.adapters.usaspending import USASpendingAdapter


class TestParse:
    def test_returns_correct_record_count(self, usaspending_response):
        adapter = USASpendingAdapter()
        records = adapter.parse(usaspending_response)
        assert len(records) == 3

    def test_native_id_is_award_id(self, usaspending_response):
        adapter = USASpendingAdapter()
        records = adapter.parse(usaspending_response)
        assert records[0].native_id == "DAAH23-26-C-0042"

    def test_source_id_is_usaspending(self, usaspending_response):
        adapter = USASpendingAdapter()
        records = adapter.parse(usaspending_response)
        for record in records:
            assert record.source_id == "usaspending"

    def test_structured_data_contains_amount(self, usaspending_response):
        adapter = USASpendingAdapter()
        records = adapter.parse(usaspending_response)
        assert records[0].structured_data["amount_usd"] == 1_100_000_000.00

    def test_structured_data_contains_recipient(self, usaspending_response):
        adapter = USASpendingAdapter()
        records = adapter.parse(usaspending_response)
        assert records[0].structured_data["recipient_name"] == "LOCKHEED MARTIN CORPORATION"

    def test_structured_data_contains_uei(self, usaspending_response):
        adapter = USASpendingAdapter()
        records = adapter.parse(usaspending_response)
        assert records[0].structured_data["recipient_uei"] == "LDHZM2EQPLG4"

    def test_structured_data_contains_agency(self, usaspending_response):
        adapter = USASpendingAdapter()
        records = adapter.parse(usaspending_response)
        assert records[0].structured_data["awarding_agency"] == "Department of Defense"

    def test_structured_data_contains_description(self, usaspending_response):
        adapter = USASpendingAdapter()
        records = adapter.parse(usaspending_response)
        assert "LRASM" in records[0].structured_data["description"]

    def test_entity_mentions_extracted(self, usaspending_response):
        adapter = USASpendingAdapter()
        records = adapter.parse(usaspending_response)
        # Each award should produce at least one entity mention (the recipient)
        assert len(records[0].entity_mentions) >= 1
        assert records[0].entity_mentions[0]["mention"] == "LOCKHEED MARTIN CORPORATION"

    def test_text_chunk_contains_key_fields(self, usaspending_response):
        adapter = USASpendingAdapter()
        records = adapter.parse(usaspending_response)
        chunk = records[0].text_chunk
        assert "LOCKHEED MARTIN" in chunk
        assert "LRASM" in chunk

    def test_record_type_is_contract_award(self, usaspending_response):
        adapter = USASpendingAdapter()
        records = adapter.parse(usaspending_response)
        for record in records:
            assert record.record_type == "contract_award"

    def test_desk_is_defense(self, usaspending_response):
        adapter = USASpendingAdapter()
        records = adapter.parse(usaspending_response)
        for record in records:
            assert "defense" in record.desk

    def test_empty_results_returns_empty_list(self):
        adapter = USASpendingAdapter()
        response = {"results": [], "page_metadata": {"has_next_page": False}, "total_count": 0}
        records = adapter.parse(response)
        assert records == []

    def test_missing_uei_does_not_raise(self, usaspending_response):
        adapter = USASpendingAdapter()
        response = json.loads(json.dumps(usaspending_response))
        del response["results"][0]["Recipient UEI"]
        records = adapter.parse(response)
        assert records[0].structured_data.get("recipient_uei") is None


class TestContentHash:
    def test_content_hash_is_deterministic(self, usaspending_response):
        adapter = USASpendingAdapter()
        records1 = adapter.parse(usaspending_response)
        records2 = adapter.parse(usaspending_response)
        for r1, r2 in zip(records1, records2):
            assert r1.content_hash == r2.content_hash

    def test_content_hash_changes_on_amount_change(self, usaspending_response):
        adapter = USASpendingAdapter()
        original = adapter.parse(usaspending_response)

        modified = json.loads(json.dumps(usaspending_response))
        modified["results"][0]["Award Amount"] = 999_999_999.00
        updated = adapter.parse(modified)

        assert original[0].content_hash != updated[0].content_hash

    def test_content_hash_is_sha256_hex(self, usaspending_response):
        adapter = USASpendingAdapter()
        records = adapter.parse(usaspending_response)
        # SHA-256 hex digest is always 64 characters
        assert len(records[0].content_hash) == 64
        assert all(c in "0123456789abcdef" for c in records[0].content_hash)


class TestCursor:
    def test_build_request_payload_uses_date_range(self):
        adapter = USASpendingAdapter()
        cursor = {"last_date": "2026-01-01"}
        payload = adapter.build_request_payload(cursor, page=1)
        assert "filters" in payload
        time_periods = payload["filters"]["time_period"]
        assert any(tp["start_date"] == "2026-01-01" for tp in time_periods)

    def test_build_request_payload_default_cursor(self):
        adapter = USASpendingAdapter()
        payload = adapter.build_request_payload(cursor=None, page=1)
        # Without cursor, should use a reasonable lookback window
        assert "filters" in payload
        assert "time_period" in payload["filters"]

    def test_next_cursor_from_response_no_next_page(self, usaspending_response):
        adapter = USASpendingAdapter()
        # has_next_page = False → cursor advances to today's date
        cursor = adapter.next_cursor(usaspending_response, current_page=1)
        assert cursor is not None
        assert "last_date" in cursor

    def test_next_cursor_from_response_has_next_page(self, usaspending_response):
        adapter = USASpendingAdapter()
        response = json.loads(json.dumps(usaspending_response))
        response["page_metadata"]["has_next_page"] = True
        cursor = adapter.next_cursor(response, current_page=1)
        assert cursor["page"] == 2


class TestDefenseTechFilter:
    """The Defense desk is scoped by technology, not agency (D059)."""

    def test_payload_includes_defense_tech_keywords(self):
        adapter = USASpendingAdapter()
        payload = adapter.build_request_payload(cursor=None, page=1)
        keywords = payload["filters"]["keywords"]
        assert keywords, "expected a non-empty defense-tech keyword filter"
        # Spot-check coverage of the operator's named themes.
        joined = " ".join(keywords).lower()
        for theme in ("satellite", "directed energy", "drone", "autonomous",
                      "radar", "guided missile", "electronic warfare"):
            assert theme in joined, f"missing defense-tech theme: {theme}"

    def test_keywords_exclude_generic_overhead_terms(self):
        # The whole point is to drop generic federal IT/admin — make sure we didn't
        # add over-broad terms that would re-admit it.
        adapter = USASpendingAdapter()
        keywords = [k.lower() for k in adapter.build_request_payload(None, 1)["filters"]["keywords"]]
        for noise in ("it services", "software", "information technology", "support services"):
            assert noise not in keywords
