"""Unit tests for name-based gazetteer linking (Convergence-graph §4 / coverage lift).

Locks the precision guards — multi-word only, word-boundary n-gram match, ambiguity drop — that
decide whether name linking lifts coverage without corrupting the graph with wrong links.
"""
from engine.entity.gazetteer import build_alias_index, find_mentions


class TestBuildAliasIndex:
    def test_keeps_multiword_alias(self):
        idx = build_alias_index([("LOCKHEED MARTIN", "e1")])
        assert idx == {"LOCKHEED MARTIN": "e1"}

    def test_drops_single_token_alias(self):
        # single-word names collide with common English → not trusted from free text
        idx = build_alias_index([("BLOCK", "e1"), ("NVIDIA", "e2")])
        assert idx == {}

    def test_drops_stopword_alias(self):
        idx = build_alias_index([("UNITED STATES", "e1")])
        assert idx == {}

    def test_same_alias_same_entity_is_kept(self):
        idx = build_alias_index([("ENERGY FUELS", "e1"), ("ENERGY FUELS", "e1")])
        assert idx == {"ENERGY FUELS": "e1"}

    def test_ambiguous_alias_dropped_entirely(self):
        # one alias → two different entities is unresolvable; drop it, don't guess
        idx = build_alias_index([
            ("ACME CORP", "e1"),
            ("ACME CORP", "e2"),
            ("ACME CORP", "e1"),  # even re-seeing e1 later must not resurrect it
        ])
        assert "ACME CORP" not in idx

    def test_blank_alias_skipped(self):
        idx = build_alias_index([("", "e1"), ("   ", "e2"), ("REAL NAME", "e3")])
        assert idx == {"REAL NAME": "e3"}


class TestFindMentions:
    IDX = {
        "LOCKHEED MARTIN": "lmt",
        "ENERGY FUELS": "uuuu",
        "ADVANCED MICRO DEVICES": "amd",
    }

    def test_matches_multiword_alias_in_prose(self):
        text = "On Tuesday, Lockheed Martin announced a new contract."
        assert find_mentions(text, self.IDX) == ["lmt"]

    def test_matches_despite_punctuation_and_case(self):
        text = "energy fuels, inc. and LOCKHEED MARTIN Corp. partnered."
        assert set(find_mentions(text, self.IDX)) == {"uuuu", "lmt"}

    def test_matches_three_token_alias(self):
        assert find_mentions("Advanced Micro Devices shipped chips", self.IDX) == ["amd"]

    def test_no_substring_false_match(self):
        # "MARTIN" alone (a person) must NOT match "LOCKHEED MARTIN"
        assert find_mentions("Martin drove the energy program", self.IDX) == []

    def test_partial_multiword_does_not_match(self):
        # "ENERGY" alone is not the alias; only the full "ENERGY FUELS" bigram links
        assert find_mentions("the energy sector grew", self.IDX) == []

    def test_deduplicates_repeated_mentions(self):
        text = "Lockheed Martin ... Lockheed Martin again ... Lockheed Martin"
        assert find_mentions(text, self.IDX) == ["lmt"]

    def test_order_preserving_unique(self):
        text = "Energy Fuels partnered with Lockheed Martin and Energy Fuels agreed."
        assert find_mentions(text, self.IDX) == ["uuuu", "lmt"]

    def test_empty_text_and_index(self):
        assert find_mentions("", self.IDX) == []
        assert find_mentions("Lockheed Martin", {}) == []
