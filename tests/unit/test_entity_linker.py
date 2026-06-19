"""Unit tests for the brief entity-linker input shaping (T3.3, D091).

The DB path (resolve_item_entities / _mint_entity) is exercised by the operator integration run;
here we lock down the pure ``extract_resolution_inputs`` mapping that decides which authoritative
identifiers each source contributes — the precision-critical part.
"""
from engine.entity.linker import extract_resolution_inputs


class TestExtractResolutionInputs:
    def test_edgar_mention_carries_ticker_and_padded_cik(self):
        mentions = [{"mention": "NuScale Power", "ticker": "smr", "cik": "1822966"}]
        out = extract_resolution_inputs("edgar", mentions, {})
        assert out == [("NuScale Power", [("ticker", "SMR"), ("cik", "0001822966")])]

    def test_already_padded_cik_unchanged(self):
        mentions = [{"mention": "Apple", "cik": "0000320193"}]
        out = extract_resolution_inputs("edgar", mentions, {})
        assert out == [("Apple", [("cik", "0000320193")])]

    def test_usaspending_uei_pulled_from_structured_data(self):
        mentions = [{"mention": "Anduril Industries"}]
        structured = {"recipient_uei": "abc123def456"}
        out = extract_resolution_inputs("usaspending", mentions, structured)
        assert out == [("Anduril Industries", [("uei", "ABC123DEF456")])]

    def test_usaspending_uei_not_duplicated_when_on_mention(self):
        mentions = [{"mention": "Foo", "uei": "XYZ"}]
        out = extract_resolution_inputs("usaspending", mentions, {"recipient_uei": "xyz"})
        assert out == [("Foo", [("uei", "XYZ")])]

    def test_non_usaspending_ignores_structured_uei(self):
        # The structured recipient_uei convention is USAspending-specific; don't read it elsewhere.
        out = extract_resolution_inputs("edgar", [{"mention": "Bar"}], {"recipient_uei": "ZZZ"})
        assert out == [("Bar", [])]

    def test_blank_mentions_skipped(self):
        mentions = [{"mention": ""}, {"mention": "   "}, {"ticker": "X"}]
        assert extract_resolution_inputs("edgar", mentions, {}) == []

    def test_empty_inputs(self):
        assert extract_resolution_inputs("edgar", None, None) == []
        assert extract_resolution_inputs("edgar", [], {}) == []

    def test_name_without_identifiers(self):
        out = extract_resolution_inputs("usaspending", [{"mention": "Mystery Co"}], {})
        assert out == [("Mystery Co", [])]
