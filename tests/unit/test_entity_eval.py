"""Resolver eval metrics (T3.2, D091) — pure."""
from engine.entity.eval import evaluate


class TestEvaluate:
    def test_all_correct(self):
        m = evaluate({"a": "LMT", "b": "PLTR"}, {"a": "LMT", "b": "PLTR"})
        assert m.precision == 1.0 and m.recall == 1.0 and m.false_link_rate == 0.0

    def test_false_link_counts_against_precision(self):
        m = evaluate({"a": "NOC"}, {"a": "LMT"})   # linked, but wrong
        assert m.resolved == 1 and m.wrong == 1 and m.correct == 0
        assert m.precision == 0.0 and m.false_link_rate == 1.0

    def test_linking_a_should_not_resolve_is_a_false_link(self):
        m = evaluate({"a": "LMT"}, {"a": None})    # expected no link, but we linked
        assert m.wrong == 1 and m.precision == 0.0

    def test_miss_hurts_recall_not_precision(self):
        m = evaluate({"a": "LMT"}, {"a": "LMT", "b": "PLTR"})   # b missed
        assert m.precision == 1.0
        assert m.recall == 0.5 and m.resolvable == 2 and m.resolved == 1

    def test_no_links_precision_vacuously_one(self):
        m = evaluate({}, {"a": "LMT"})
        assert m.precision == 1.0 and m.recall == 0.0 and m.resolved == 0
