"""hpi-worker ingest loop (D116).

The worker owns GDELT (a shared CI IP gets 429'd). `ingest_once` must ingest every
worker-owned source and — critically — NEVER raise, so one bad pull can't crash the
always-on scheduler into a Fly restart-loop. `worker/` isn't on the path by default.
"""
import sys
from pathlib import Path

import pytest

_WORKER = Path(__file__).resolve().parents[2] / "worker"
if str(_WORKER) not in sys.path:
    sys.path.insert(0, str(_WORKER))

from tasks import app  # noqa: E402


class _Result:
    def __init__(self, status):
        self.status = status
        self.records_new = 3
        self.records_fetched = 5


def test_worker_owns_gdelt_only():
    # The whole point of the worker: GDELT off CI (D116). Guard against silently widening it.
    assert app.WORKER_SOURCES == ("gdelt",)


def test_interval_defaults_and_floor(monkeypatch):
    monkeypatch.delenv("WORKER_INGEST_INTERVAL_SECONDS", raising=False)
    assert app._interval_seconds() == app.DEFAULT_INTERVAL_SECONDS
    monkeypatch.setenv("WORKER_INGEST_INTERVAL_SECONDS", "5")
    assert app._interval_seconds() == 60          # floored so a bad value can't busy-loop
    monkeypatch.setenv("WORKER_INGEST_INTERVAL_SECONDS", "garbage")
    assert app._interval_seconds() == app.DEFAULT_INTERVAL_SECONDS


async def test_ingest_once_runs_each_source(monkeypatch):
    called = []

    async def fake_run_source(sid, pool, *, fetcher, embed):
        called.append(sid)
        return _Result("success")

    monkeypatch.setattr(app, "run_source", fake_run_source)
    statuses = await app.ingest_once(pool=object(), embed=False)
    assert called == list(app.WORKER_SOURCES)
    assert statuses == ["success"]


async def test_ingest_once_swallows_a_failing_source(monkeypatch):
    # A raising source must be caught (logged as failed), never propagated — the scheduler
    # loop has to survive it.
    async def boom(sid, pool, *, fetcher, embed):
        raise RuntimeError("gdelt 429")

    monkeypatch.setattr(app, "run_source", boom)
    statuses = await app.ingest_once(pool=object(), embed=False)  # must not raise
    assert statuses == ["failed"]
