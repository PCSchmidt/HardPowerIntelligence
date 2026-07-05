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

    def test_record_type_is_federal_award(self, usaspending_response):
        adapter = USASpendingAdapter()
        records = adapter.parse(usaspending_response)
        for record in records:
            assert record.record_type == "federal_award"

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


class TestRecencyGuard:
    """D123: a decades-old parent/ceiling award resurfacing on a recent mod is not news today."""

    def _row(self, award_id: str, start: str) -> dict:
        return {"Award ID": award_id, "Recipient Name": "THE BOEING COMPANY",
                "Award Amount": 22_000_000_000.0, "Start Date": start, "End Date": "2026-09-30"}

    def test_legacy_award_dropped(self):
        # The real 7/5 case: a 1993-dated $22B NASA ceiling.
        resp = {"results": [self._row("LEGACY", "1993-11-15")]}
        assert USASpendingAdapter().parse(resp) == []

    def test_recent_award_kept(self):
        resp = {"results": [self._row("FRESH", "2026-02-01")]}
        assert len(USASpendingAdapter().parse(resp)) == 1

    def test_missing_start_date_fails_open(self):
        row = self._row("NODATE", "")
        row.pop("Start Date")
        assert len(USASpendingAdapter().parse({"results": [row]})) == 1

    def test_unparseable_start_date_fails_open(self):
        assert len(USASpendingAdapter().parse({"results": [self._row("BAD", "None")]})) == 1


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
    def test_build_request_payload_ignores_cursor_date_uses_rolling_lookback(self):
        # USAspending awards lag (action date appears in the API weeks later), so the window is a
        # FIXED rolling lookback every run, not a forward watermark — a stale cursor date that
        # shrank the window to ~1 day caused the source to silently fetch 0 (Phase B fix).
        from datetime import date, timedelta
        from engine.adapters.usaspending import _LOOKBACK_DAYS

        adapter = USASpendingAdapter()
        payload = adapter.build_request_payload({"last_date": "2026-01-01"}, page=1)
        tp = payload["filters"]["time_period"][0]
        expected_start = (date.today() - timedelta(days=_LOOKBACK_DAYS)).isoformat()
        assert tp["start_date"] == expected_start      # rolling lookback, not the cursor date
        assert tp["start_date"] != "2026-01-01"        # stale watermark is ignored
        assert tp["end_date"] == date.today().isoformat()

    def test_build_request_payload_default_cursor(self):
        adapter = USASpendingAdapter()
        payload = adapter.build_request_payload(cursor=None, page=1)
        # Without cursor, should use the same rolling lookback window
        assert "filters" in payload
        assert "time_period" in payload["filters"]

    def test_next_cursor_walks_probes(self, usaspending_response):
        adapter = USASpendingAdapter()
        # Within a run, next_cursor advances through probes by page index.
        assert adapter.next_cursor(usaspending_response, current_page=1) == {"page": 2}

    def test_next_cursor_terminal_after_last_probe(self, usaspending_response):
        adapter = USASpendingAdapter()
        cursor = adapter.next_cursor(usaspending_response, current_page=adapter.probe_count)
        assert "last_date" in cursor


class TestProbesAndDesks:
    """USAspending is cross-desk: each probe tags records to the desk(s) it serves,
    so it's a daily feed of government capital formation across all three (D059/D064).
    Probe order (D065): 1 space→def∩ai, 2 kinetic→def, 3 autonomy→def∩ai,
    4 AI compute→ai, 5 energy→energy, 6 rare earth→def∩ai∩energy."""

    def test_six_probes(self):
        assert USASpendingAdapter().probe_count == 6

    def test_default_probe_is_space_defense_ai(self, usaspending_response):
        # parse() without build uses probe[0] (space → Defense∩AI, D065).
        records = USASpendingAdapter().parse(usaspending_response)
        assert set(records[0].desk) == {"defense", "ai"}

    def test_space_probe_keywords(self):
        adapter = USASpendingAdapter()
        kw = " ".join(adapter.build_request_payload(None, page=1)["filters"]["keywords"]).lower()
        for theme in ("satellite", "spacecraft", "launch vehicle", "geospatial"):
            assert theme in kw, f"missing space theme: {theme}"

    def test_kinetic_defense_probe_keywords(self):
        adapter = USASpendingAdapter()
        kw = " ".join(adapter.build_request_payload(None, page=2)["filters"]["keywords"]).lower()
        for theme in ("directed energy", "drone", "radar", "guided missile",
                      "electronic warfare"):
            assert theme in kw, f"missing defense-tech theme: {theme}"

    def test_kinetic_probe_is_defense_only(self, usaspending_response):
        adapter = USASpendingAdapter()
        adapter.build_request_payload(None, page=2)  # kinetic & sensing defense
        records = adapter.parse(usaspending_response)
        assert set(records[0].desk) == {"defense"}

    def test_autonomy_probe_is_defense_ai(self, usaspending_response):
        adapter = USASpendingAdapter()
        adapter.build_request_payload(None, page=3)  # autonomy / AI-for-defense
        records = adapter.parse(usaspending_response)
        assert set(records[0].desk) == {"defense", "ai"}

    def test_ai_probe_tags_ai(self, usaspending_response):
        adapter = USASpendingAdapter()
        adapter.build_request_payload(None, page=4)  # AI compute build-out
        records = adapter.parse(usaspending_response)
        assert set(records[0].desk) == {"ai"}

    def test_energy_probe_tags_energy(self, usaspending_response):
        adapter = USASpendingAdapter()
        adapter.build_request_payload(None, page=5)  # energy transformation
        records = adapter.parse(usaspending_response)
        assert set(records[0].desk) == {"energy"}

    def test_convergence_probe_tags_all_three(self, usaspending_response):
        adapter = USASpendingAdapter()
        adapter.build_request_payload(None, page=6)  # rare earth / critical minerals
        records = adapter.parse(usaspending_response)
        assert set(records[0].desk) == {"defense", "ai", "energy"}

    def test_defense_probes_use_contracts_ai_energy_use_grants(self):
        # Capital formation differs by desk: defense = procurement contracts (A-D);
        # AI/Energy research+buildout = grants/assistance (02-05). Per-probe award types (D064).
        adapter = USASpendingAdapter()
        space = adapter.build_request_payload(None, page=1)["filters"]["award_type_codes"]
        kinetic = adapter.build_request_payload(None, page=2)["filters"]["award_type_codes"]
        ai = adapter.build_request_payload(None, page=4)["filters"]["award_type_codes"]
        energy = adapter.build_request_payload(None, page=5)["filters"]["award_type_codes"]
        assert set(space) == {"A", "B", "C", "D"}
        assert set(kinetic) == {"A", "B", "C", "D"}
        assert set(ai) == {"02", "03", "04", "05"}
        assert set(energy) == {"02", "03", "04", "05"}

    def test_probe_keyword_sets_are_disjoint(self):
        # Disjoint keyword sets keep a record's desk tag deterministic under dedup.
        from engine.adapters.usaspending import _PROBES
        seen: set[str] = set()
        for probe in _PROBES:
            for k in probe.keywords:
                assert k not in seen, f"keyword {k!r} appears in multiple probes"
                seen.add(k)

    def test_keywords_exclude_generic_overhead_terms(self):
        # The whole point is to drop generic federal IT/admin across every probe.
        adapter = USASpendingAdapter()
        all_kw = []
        for page in range(1, adapter.probe_count + 1):
            payload = adapter.build_request_payload(None, page)
            all_kw += [k.lower() for k in payload["filters"]["keywords"]]
        for noise in ("it services", "software", "information technology", "support services"):
            assert noise not in all_kw
