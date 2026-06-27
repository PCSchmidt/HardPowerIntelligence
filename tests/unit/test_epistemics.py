"""Epistemic framing taxonomy (D098).

Spec: every item carries a deterministic attribution/confidence label derived from
(a) the source's evidence class and (b) whether the claim was citation-supported —
NO LLM, no new fabrication surface. The label is transparency about the basis, the
keystone of "widen the net": under-grounded primary-record claims are now LABELED
(ANALYSIS) instead of dropped, while signal/reported sources cap below CONFIRMED.
"""
from engine.brief.epistemics import (
    Attribution,
    classify_item,
    evidence_class,
)


class TestAttributionLadder:
    def test_ranks_strictly_decrease_confirmed_to_speculative(self):
        order = [
            Attribution.CONFIRMED,
            Attribution.REPORTED,
            Attribution.ANALYSIS,
            Attribution.SPECULATIVE,
        ]
        ranks = [a.rank for a in order]
        assert ranks == sorted(ranks, reverse=True)
        assert len(set(ranks)) == 4  # all distinct

    def test_serializes_to_its_string_value(self):
        # str-enum so it persists / crosses the API as a plain string.
        assert Attribution.CONFIRMED == "confirmed"
        assert Attribution.ANALYSIS.value == "analysis"

    def test_every_tier_has_label_and_description(self):
        for a in Attribution:
            assert a.label and a.description


class TestEvidenceClass:
    def test_primary_record_sources_are_primary(self):
        for src in ("usaspending", "edgar", "nrc", "arxiv", "congress_gov"):
            assert evidence_class(src) == "primary"

    def test_gdelt_is_signal(self):
        assert evidence_class("gdelt") == "signal"

    def test_unknown_source_defaults_to_reported_not_primary(self):
        # The honest default: never silently grant primary/confirmed standing to a
        # source we haven't deliberately classified.
        assert evidence_class("some_future_ai_newsroom_rss") == "reported"


class TestClassifyItem:
    def test_primary_and_cited_is_confirmed(self):
        e = classify_item(source_id="usaspending", citation_supported=True)
        assert e.attribution is Attribution.CONFIRMED
        assert e.confidence == 4
        assert e.label == "Confirmed"

    def test_primary_but_uncited_is_analysis_not_dropped(self):
        # The core of the widen-the-net flip: the old gate dropped this sentence;
        # now we keep it and label it HPI analysis.
        e = classify_item(source_id="edgar", citation_supported=False)
        assert e.attribution is Attribution.ANALYSIS

    def test_signal_source_caps_at_speculative(self):
        e = classify_item(source_id="gdelt", citation_supported=True)
        assert e.attribution is Attribution.SPECULATIVE

    def test_reported_source_caps_at_reported_even_when_cited(self):
        e = classify_item(source_id="future_newsroom", citation_supported=True)
        assert e.attribution is Attribution.REPORTED

    def test_analysis_only_is_analysis_regardless_of_source(self):
        e = classify_item(
            source_id="usaspending", citation_supported=True, analysis_only=True
        )
        assert e.attribution is Attribution.ANALYSIS
