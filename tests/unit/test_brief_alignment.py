"""Passage/fact alignment for multi-source briefs (D068).

The bug: the citation pool (RAG, similarity-ranked) and the verified facts
(materiality, $-ranked) were computed independently, so a high-volume source
(arXiv) hijacked retrieval and the high-$ capital facts had no passage to cite —
they were all excluded at eval. These pure helpers fix the seam:

- _select_facts: top-by-materiality with an advancement floor (capital must not
  crowd out the technology leg, D063);
- _candidate_passages: a citable passage per material fact;
- _merge_passages: union fact + RAG passages, dedup, re-index for [CITE:N].

Invariant: every verified fact has a citable passage.
"""
from datetime import datetime, timezone

from engine.brief.generator import (
    _candidate_passages,
    _merge_passages,
    _select_facts,
)
from engine.brief.rag import PassageContext

NOW = datetime.now(timezone.utc)


def _cand(rr_id: str, record_type: str, score: float) -> tuple[dict, float]:
    return (
        {
            "rr_id": rr_id,
            "source_id": "src",
            "record_type": record_type,
            "url": f"https://x/{rr_id}",
            "native_id": f"native-{rr_id}",
            "fetched_at": NOW,
            "text_chunk": f"chunk-{rr_id}",
            "structured_data": {},
        },
        score,
    )


# materiality-sorted: 4 capital (high) then 2 advancement (low)
CANDIDATES = [
    _cand("c1", "federal_award", 0.90),
    _cand("c2", "federal_award", 0.80),
    _cand("c3", "federal_award", 0.70),
    _cand("c4", "filing", 0.60),
    _cand("a1", "research_paper", 0.55),
    _cand("a2", "research_paper", 0.54),
]


def _ids(facts):
    return [c[0]["rr_id"] for c in facts]


class TestSelectFacts:
    def test_floor_reserves_advancement_slots(self):
        # limit 4, floor 3 but only 2 advancement available → both included.
        facts = _select_facts(CANDIDATES, limit=4, advancement_floor=3)
        assert len(facts) == 4
        adv = [c for c in facts if c[0]["record_type"] == "research_paper"]
        assert len(adv) == 2

    def test_floor_zero_is_pure_materiality(self):
        facts = _select_facts(CANDIDATES, limit=4, advancement_floor=0)
        assert _ids(facts) == ["c1", "c2", "c3", "c4"]

    def test_partial_floor_keeps_top_capital(self):
        # floor 1 → 1 advancement (top adv = a1) + top 3 capital, materiality order.
        facts = _select_facts(CANDIDATES, limit=4, advancement_floor=1)
        assert _ids(facts) == ["c1", "c2", "c3", "a1"]

    def test_output_preserves_materiality_order(self):
        facts = _select_facts(CANDIDATES, limit=4, advancement_floor=2)
        assert _ids(facts) == ["c1", "c2", "a1", "a2"]

    def test_limit_caps_total(self):
        assert len(_select_facts(CANDIDATES, limit=2, advancement_floor=3)) == 2

    def test_tops_up_when_capital_scarce(self):
        # Only 1 capital record but limit 3 → fill remaining with advancement.
        cands = [_cand("c1", "federal_award", 0.9),
                 _cand("a1", "research_paper", 0.5),
                 _cand("a2", "research_paper", 0.4)]
        facts = _select_facts(cands, limit=3, advancement_floor=0)
        assert len(facts) == 3
        assert "c1" in _ids(facts)


class TestCandidatePassages:
    def test_one_passage_per_fact_with_excerpt(self):
        facts = _select_facts(CANDIDATES, limit=3, advancement_floor=1)
        passages = _candidate_passages(facts)
        assert len(passages) == len(facts)
        for p, (c, _) in zip(passages, facts):
            assert isinstance(p, PassageContext)
            assert p.raw_record_id == c["rr_id"]
            assert p.excerpt == c["text_chunk"]
            assert p.url == c["url"]


class TestMergePassages:
    def _rag(self, rr_id, excerpt):
        return PassageContext(99, rr_id, "src", "u", NOW, "n", excerpt)

    def test_reindexed_contiguously(self):
        fp = _candidate_passages(_select_facts(CANDIDATES, 3, 1))
        merged = _merge_passages(fp, [self._rag("r9", "rag")], cap=10)
        assert [p.index for p in merged] == list(range(1, len(merged) + 1))

    def test_dedup_fact_passage_wins(self):
        fp = _candidate_passages([_cand("c1", "federal_award", 0.9)])
        rag = [self._rag("c1", "RAG VERSION"), self._rag("r9", "new")]
        merged = _merge_passages(fp, rag, cap=10)
        rids = [p.raw_record_id for p in merged]
        assert rids.count("c1") == 1            # deduped
        assert "r9" in rids                      # new context kept
        c1 = next(p for p in merged if p.raw_record_id == "c1")
        assert c1.excerpt == "chunk-c1"          # fact passage won, not RAG

    def test_cap_respected(self):
        fp = _candidate_passages(_select_facts(CANDIDATES, 4, 1))
        merged = _merge_passages(fp, [self._rag("r9", "x")], cap=2)
        assert len(merged) == 2

    def test_every_fact_has_a_citable_passage(self):
        # The core invariant: each verified fact's record appears in the passages.
        facts = _select_facts(CANDIDATES, limit=4, advancement_floor=2)
        fp = _candidate_passages(facts)
        rag = [self._rag("r9", "context")]
        merged = _merge_passages(fp, rag, cap=20)
        passage_ids = {p.raw_record_id for p in merged}
        for c, _ in facts:
            assert c["rr_id"] in passage_ids
