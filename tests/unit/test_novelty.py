"""
Tests for the novelty / anti-rehash gate (D074): apply_novelty_penalty down-ranks
records already featured in recent published briefs so fresh items lead, while
demoting (not dropping) so a long-lived item can still re-lead when nothing fresher
is material. Pure function — no DB.
"""
from engine.brief.generator import _novelty_key, apply_novelty_penalty


def _row(source_id, native_id):
    return {"source_id": source_id, "native_id": native_id}


class TestNoveltyKey:
    def test_combines_source_and_native_id(self):
        key = _novelty_key({"source_id": "usaspending", "native_id": "ABC-1"})
        assert key == "usaspending:ABC-1"

    def test_missing_fields_default_empty(self):
        assert _novelty_key({}) == ":"


class TestApplyNoveltyPenalty:
    def test_featured_record_is_demoted_below_fresh(self):
        boeing = _row("usaspending", "NASA-22B")   # huge, but already featured
        fresh = _row("edgar", "8K-NEW")            # smaller, but new
        candidates = [(boeing, 0.9), (fresh, 0.5)]
        featured = {"usaspending:NASA-22B"}
        out = apply_novelty_penalty(candidates, featured, penalty=0.5)
        # 0.9 * 0.5 = 0.45 < 0.5 → fresh now leads
        assert out[0][0] is fresh
        assert out[1][0] is boeing
        assert out[1][1] == 0.45

    def test_non_featured_scores_unchanged(self):
        a, b = _row("edgar", "x"), _row("arxiv", "y")
        out = apply_novelty_penalty([(a, 0.6), (b, 0.4)], {"usaspending:other"}, penalty=0.5)
        assert out == [(a, 0.6), (b, 0.4)]

    def test_penalty_one_is_noop(self):
        a = _row("edgar", "x")
        candidates = [(a, 0.6)]
        assert apply_novelty_penalty(candidates, {"edgar:x"}, penalty=1.0) is candidates

    def test_empty_featured_is_noop(self):
        a = _row("edgar", "x")
        candidates = [(a, 0.6)]
        assert apply_novelty_penalty(candidates, set(), penalty=0.5) is candidates

    def test_demoted_item_still_leads_when_nothing_fresher(self):
        # Only a recently-featured item is material — it must remain (no empty brief),
        # just with a reduced score. Anti-rehash demotes; it never strands the desk.
        only = _row("usaspending", "NASA-22B")
        out = apply_novelty_penalty([(only, 0.9)], {"usaspending:NASA-22B"}, penalty=0.5)
        assert len(out) == 1
        assert out[0][0] is only
        assert out[0][1] == 0.45

    def test_resorts_by_adjusted_score(self):
        # Two featured + one fresh; result strictly ordered by post-penalty score.
        x = _row("a", "1")   # 0.8 featured → 0.4
        y = _row("b", "2")   # 0.7 fresh    → 0.7
        z = _row("c", "3")   # 0.6 featured → 0.3
        out = apply_novelty_penalty(
            [(x, 0.8), (y, 0.7), (z, 0.6)], {"a:1", "c:3"}, penalty=0.5,
        )
        assert [r[0] for r in out] == [y, x, z]
        assert [round(r[1], 3) for r in out] == [0.7, 0.4, 0.3]
