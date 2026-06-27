"""Epistemic framing — confidence + attribution on every brief item (D098).

This is the keystone of "widen the net" (information-philosophy, 2026-06-27). The
operator retired *"every claim cites the public record"* as an **admission gate**:
that doctrine excluded vast amounts of important-but-not-pristinely-citable signal
for very small benefit. The replacement is **honesty over exclusion** — cast the net
wide, then *grade and attribute every item transparently* so the reader sees the
**basis and confidence**, the way real intelligence analysis uses estimative language.

This module is the deterministic vocabulary for that grading. It does NOT call an LLM
and introduces no new fabrication surface: an item's attribution is derived from facts
already known in the pipeline — which source produced it, and whether its claims were
citation-supported by the grounding eval. The label is *transparency about the basis*,
never a gate that withholds. The only hard line stays elsewhere: don't fabricate
(``CitationEvaluator.eval_analysis`` flags invented specifics; D071/D073).

Later gates consume this: the publish path flips from *suppress under-grounded* to
*label it* (D070's claim-floor becomes a confidence signal, not a drop), persistence
stores the label, and the reader renders it.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Attribution(str, Enum):
    """The basis on which an item's central facts are evidenced — one ordered ladder
    of decreasing certainty, shown to the reader as estimative framing.

    Ordered most- to least- certain; ``rank`` exposes that order numerically. A
    ``str`` enum so the value serializes directly to JSON / the DB / the API.
    """

    CONFIRMED = "confirmed"      # primary public record, claim citation-supported
    REPORTED = "reported"        # attributed third-party reporting (named, not primary)
    ANALYSIS = "analysis"        # HPI synthesis/inference over the record(s)
    SPECULATIVE = "speculative"  # early/weak signal, worth watching, low confidence

    @property
    def rank(self) -> int:
        """Confidence rank, higher = more certain (CONFIRMED 4 … SPECULATIVE 1)."""
        return _RANK[self]

    @property
    def label(self) -> str:
        """Short reader-facing chip text."""
        return _LABEL[self]

    @property
    def description(self) -> str:
        """One-line explanation of what the basis means, for a legend/tooltip."""
        return _DESCRIPTION[self]


_RANK: dict[Attribution, int] = {
    Attribution.CONFIRMED: 4,
    Attribution.REPORTED: 3,
    Attribution.ANALYSIS: 2,
    Attribution.SPECULATIVE: 1,
}

_LABEL: dict[Attribution, str] = {
    Attribution.CONFIRMED: "Confirmed",
    Attribution.REPORTED: "Reported",
    Attribution.ANALYSIS: "HPI analysis",
    Attribution.SPECULATIVE: "Speculative",
}

_DESCRIPTION: dict[Attribution, str] = {
    Attribution.CONFIRMED:
        "Drawn from a primary public record (a filing, award, or regulatory document) "
        "and supported by the cited source.",
    Attribution.REPORTED:
        "Attributed to third-party reporting — named, but not a primary record we hold.",
    Attribution.ANALYSIS:
        "HPI's own synthesis or inference connecting the underlying records; "
        "interpretation, clearly hedged, not a sourced fact.",
    Attribution.SPECULATIVE:
        "An early or weak signal worth watching; low confidence, not yet corroborated.",
}


# Which class of evidence a source contributes. A "primary" source can reach CONFIRMED
# when its claims are citation-supported; a "reported" source (named third-party
# reporting — private-AI newsroom RSS, DoD press releases — landing in P3) caps at
# REPORTED however well-cited, because it isn't a primary record; a "signal" source
# (GDELT, D082) is radar, never a cited fact, so it caps at SPECULATIVE.
PRIMARY = "primary"
REPORTED = "reported"
SIGNAL = "signal"

_SOURCE_EVIDENCE: dict[str, str] = {
    "usaspending": PRIMARY,
    "dod_contracts": PRIMARY,
    "sam_gov": PRIMARY,
    "congress_gov": PRIMARY,
    "fred": PRIMARY,
    "edgar": PRIMARY,
    "nrc": PRIMARY,
    "arxiv": PRIMARY,
    "gdelt": SIGNAL,
}


def evidence_class(source_id: str) -> str:
    """The evidence class a source contributes.

    An UNCLASSIFIED source defaults to ``REPORTED``, not ``PRIMARY`` — the honest
    default. We never silently grant "confirmed/primary" standing to a source we
    haven't deliberately classified as a primary public record; widening the net
    must not quietly inflate confidence.
    """
    return _SOURCE_EVIDENCE.get(source_id, REPORTED)


@dataclass(frozen=True)
class ItemEpistemics:
    """The epistemic framing attached to one item: its attribution and confidence."""

    attribution: Attribution

    @property
    def confidence(self) -> int:
        return self.attribution.rank

    @property
    def label(self) -> str:
        return self.attribution.label


def classify_item(
    *,
    source_id: str,
    citation_supported: bool,
    analysis_only: bool = False,
) -> ItemEpistemics:
    """Derive an item's epistemic framing from pipeline-known signals only (no LLM).

    - ``analysis_only`` (the item is HPI interpretation with no primary fact of its
      own) → ANALYSIS, regardless of source.
    - A ``signal`` source (GDELT) → SPECULATIVE — radar, never a cited fact (D082).
    - A ``reported`` source → REPORTED — attributed, but not a primary record, so it
      caps there even when its sentences are citation-clean.
    - A ``primary`` source → CONFIRMED when the claim is citation-supported, else
      ANALYSIS: we hold the primary record, but *this* sentence wasn't individually
      source-supported, so it's our reading of the record, not a sourced fact. Under
      the old gate that sentence was *dropped* (D069); now it's *kept and labeled*.
    """
    if analysis_only:
        return ItemEpistemics(Attribution.ANALYSIS)

    evidence = evidence_class(source_id)
    if evidence == SIGNAL:
        return ItemEpistemics(Attribution.SPECULATIVE)
    if evidence == REPORTED:
        return ItemEpistemics(Attribution.REPORTED)
    # PRIMARY
    if citation_supported:
        return ItemEpistemics(Attribution.CONFIRMED)
    return ItemEpistemics(Attribution.ANALYSIS)
