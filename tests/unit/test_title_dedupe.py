"""Near-duplicate title collapse (D135).

Syndicated wire news (GDELT especially) repeats one story across dozens of outlets, each a
distinct native_id that the ingest-level dedup can't catch. `dedupe_by_title` collapses exact
normalized-headline matches, keeping the highest-scoring copy, without merging distinct stories.
"""
from engine.brief.generator import _norm_title, dedupe_by_title


def _c(text, score):
    return ({"text_chunk": text, "source_id": "gdelt"}, score)


class TestNormTitle:
    def test_strips_station_suffix_and_punctuation(self):
        base = _norm_title("Trump Revives Calls For U . S . Control Of Greenland")
        suffixed = _norm_title("Trump Revives Calls For U . S . Control Of Greenland | KFYR 550 AM / 99 . 7 FM")
        assert base == suffixed == "trump revives calls for u s control of greenland"

    def test_uses_first_line_only(self):
        assert _norm_title("Headline here\nbody paragraph that differs") == "headline here"

    def test_blank_is_empty(self):
        assert _norm_title("") == ""
        assert _norm_title("   \n  ") == ""

    def test_keeps_digits_so_variants_stay_distinct(self):
        assert _norm_title("F - 35 sale to Turkey") != _norm_title("F - 22 sale to Turkey")


class TestDedupeByTitle:
    def test_collapses_syndicated_copies_to_one(self):
        greenland = "Trump Revives Calls For U . S . Control Of Greenland"
        cands = [
            _c(greenland, 0.5),
            _c(greenland + " | News Radio 105 . 5 WERC", 0.4),
            _c(greenland + " | PowerTalk 1460 AM", 0.3),
        ]
        out = dedupe_by_title(cands)
        assert len(out) == 1

    def test_keeps_highest_scoring_copy(self):
        greenland = "Trump Revives Calls For U . S . Control Of Greenland"
        cands = [_c(greenland, 0.3), _c(greenland + " | WERC", 0.9), _c(greenland, 0.2)]
        out = dedupe_by_title(cands)
        assert len(out) == 1
        assert out[0][1] == 0.9

    def test_preserves_distinct_stories(self):
        cands = [
            _c("Canada picks TKMS for submarine buy", 0.6),
            _c("Lockheed Martin to acquire Ultra Maritime", 0.7),
            _c("GCAP fighter program pushes ahead", 0.5),
        ]
        assert len(dedupe_by_title(cands)) == 3

    def test_never_collapses_blank_titles(self):
        cands = [_c("", 0.1), _c("   ", 0.2), _c(None, 0.3)]
        assert len(dedupe_by_title(cands)) == 3

    def test_representative_holds_at_first_position(self):
        # First-seen slot is retained (stable), even when a later copy scores higher.
        a = "Alpha story"
        cands = [_c("Zeta story", 0.4), _c(a, 0.2), _c(a + " | Radio", 0.9)]
        out = dedupe_by_title(cands)
        assert [o[0]["text_chunk"] for o in out][0] == "Zeta story"
        # the Alpha slot carries the better-scoring copy
        alpha = [o for o in out if _norm_title(o[0]["text_chunk"]) == "alpha story"][0]
        assert alpha[1] == 0.9

    def test_empty_input(self):
        assert dedupe_by_title([]) == []
