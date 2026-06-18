"""Resolver accuracy metrics (T3.2, D091) — the eval gate's math, pure and testable.

The resolver's job is *trust*: a wrong link (a wrong ticker on a real item) is worse than a
missed one. So the headline metric is **precision** (of the mentions we linked, what fraction
were right); **false_link_rate** is its complement. Recall is reported but not gated — v1 trades
recall for precision on purpose. ``scripts/eval_resolver.py`` runs this against the golden set
and fails if precision drops below ``entity_resolver_min_precision``.

Labels are opaque (tickers in the golden set, but any stable id works). A golden value of
``None`` means "should NOT resolve" — linking it anyway is a false link.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EvalMetrics:
    total: int          # golden entries
    resolvable: int     # golden entries that SHOULD resolve (expected is not None)
    resolved: int       # predictions that linked (pred is not None)
    correct: int        # linked AND pred == expected
    wrong: int          # linked AND pred != expected (false link, incl. linking a should-not)

    @property
    def precision(self) -> float:
        """Of what we linked, how much was right. Vacuously 1.0 if we linked nothing."""
        return self.correct / self.resolved if self.resolved else 1.0

    @property
    def false_link_rate(self) -> float:
        return self.wrong / self.resolved if self.resolved else 0.0

    @property
    def recall(self) -> float:
        """Of what should resolve, how much we caught. 1.0 if nothing should resolve."""
        return self.correct / self.resolvable if self.resolvable else 1.0

    def summary(self) -> str:
        return (
            f"total={self.total} resolvable={self.resolvable} resolved={self.resolved} "
            f"correct={self.correct} wrong={self.wrong} | "
            f"precision={self.precision:.3f} recall={self.recall:.3f} "
            f"false_link_rate={self.false_link_rate:.3f}"
        )


def evaluate(
    predictions: dict[str, str | None],
    golden: dict[str, str | None],
) -> EvalMetrics:
    """Compare predicted labels to the golden set, keyed by mention.

    A mention missing from ``predictions`` counts as not-linked (None)."""
    total = len(golden)
    resolvable = sum(1 for v in golden.values() if v is not None)
    resolved = correct = wrong = 0
    for mention, expected in golden.items():
        pred = predictions.get(mention)
        if pred is None:
            continue
        resolved += 1
        if pred == expected:
            correct += 1
        else:
            wrong += 1
    return EvalMetrics(total, resolvable, resolved, correct, wrong)
