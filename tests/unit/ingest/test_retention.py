"""Retention pruning: window math + return shape.

The NOT-EXISTS guards (don't delete cited/referenced raw_records) are SQL and are
validated end-to-end against a real DB in the live ingestion proving run; here we
verify the function computes the cutoff from `days` and returns labelled counts.
"""
from datetime import datetime, timedelta, timezone

from engine.ingest.retention import prune_hot_window


class _Txn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class RetConn:
    def __init__(self, counts):
        self._counts = list(counts)
        self.cutoffs: list[datetime] = []

    async def fetchval(self, sql, *args):
        self.cutoffs.append(args[0])  # first arg is the cutoff timestamp
        return self._counts.pop(0)

    def transaction(self):
        return _Txn()


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *a):
        return False


class RetPool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


async def test_returns_labelled_counts():
    conn = RetConn(counts=[7, 4])  # normalized deleted, then raw deleted
    result = await prune_hot_window(RetPool(conn), days=21)
    assert result == {"normalized_records": 7, "raw_records": 4}


async def test_cutoff_derived_from_days():
    conn = RetConn(counts=[0, 0])
    before = datetime.now(timezone.utc) - timedelta(days=21)
    await prune_hot_window(RetPool(conn), days=21)
    after = datetime.now(timezone.utc) - timedelta(days=21)
    # Both deletes use the same ~now-21d cutoff.
    for cutoff in conn.cutoffs:
        assert before <= cutoff <= after
    assert len(conn.cutoffs) == 2
