"""Ingest exit-code resilience (D079).

A transient single-source outage (e.g. SEC EFTS 500s) must not abort the daily job —
briefs still publish from data already in the DB. Only a total ingest failure exits
non-zero. scripts/ isn't a package, so prepend it to sys.path.
"""
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from run_ingest import decide_exit_code  # noqa: E402


def test_all_failed_is_nonzero():
    assert decide_exit_code(["failed", "failed"]) == 1


def test_partial_failure_is_zero():
    # the real case: EDGAR 500s but arxiv/usaspending succeed → keep going
    assert decide_exit_code(["failed", "success", "success"]) == 0


def test_all_success_is_zero():
    assert decide_exit_code(["success", "success"]) == 0


def test_skipped_counts_as_not_total_failure():
    assert decide_exit_code(["failed", "skipped"]) == 0


def test_empty_is_zero():
    assert decide_exit_code([]) == 0


def test_single_source_failed_is_nonzero():
    # `--source edgar` alone failing IS a total failure of what was asked.
    assert decide_exit_code(["failed"]) == 1
