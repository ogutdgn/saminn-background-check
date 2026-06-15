"""Orchestrator — fan-out, completion-order streaming, failure isolation, timeout, audit.

Uses in-process stub adapters (no network) so the engine's behaviour is deterministic.
"""
import asyncio

import pytest

from adapters.base import (
    Adapter,
    AdapterStatus,
    InmateRecord,
    SearchQuery,
)
from core.audit import AuditLog
from core.orchestrator import run_search


class StubAdapter(Adapter):
    transport = "http"
    tier = 1

    def __init__(self, id, *, delay=0.0, status=AdapterStatus.OK, records=0, raises=None):
        self.id = id
        self.display_name = id.title()
        self._delay = delay
        self._status = status
        self._records = records
        self._raises = raises

    async def search(self, query, ctx):
        await asyncio.sleep(self._delay)
        if self._raises is not None:
            raise self._raises
        recs = [InmateRecord(source=self.id, name=f"X{i}") for i in range(self._records)]
        return self._result(self._status, records=recs)

    # tiny helper to build a result without repeating the envelope
    def _result(self, status, records):
        from adapters.base import AdapterResult

        return AdapterResult(
            source=self.id,
            display_name=self.display_name,
            status=status,
            records=records,
            duration_ms=int(self._delay * 1000),
        )


async def _collect(query, **kw):
    return [r async for r in run_search(query, **kw)]


@pytest.mark.asyncio
async def test_streams_in_completion_order_fast_first():
    slow = StubAdapter("slow", delay=0.10, records=2)
    fast = StubAdapter("fast", delay=0.01, records=1)
    out = await _collect(SearchQuery(last="x"), adapters=[slow, fast])
    # fast finishes first even though it was listed second
    assert [r.source for r in out] == ["fast", "slow"]


@pytest.mark.asyncio
async def test_one_failure_is_isolated():
    good = StubAdapter("good", records=1)
    bad = StubAdapter("bad", raises=RuntimeError("boom"))
    out = {r.source: r for r in await _collect(SearchQuery(last="x"), adapters=[good, bad])}
    assert out["good"].status == AdapterStatus.OK and len(out["good"].records) == 1
    assert out["bad"].status == AdapterStatus.ERROR and "boom" in out["bad"].error


@pytest.mark.asyncio
async def test_hanging_adapter_times_out_without_blocking_others():
    hang = StubAdapter("hang", delay=5.0)
    fast = StubAdapter("fast", records=1)
    out = {r.source: r for r in await _collect(SearchQuery(last="x"), adapters=[hang, fast], timeout_s=0.05)}
    assert out["fast"].status == AdapterStatus.OK
    assert out["hang"].status == AdapterStatus.TIMEOUT


@pytest.mark.asyncio
async def test_no_sources_yields_nothing():
    assert await _collect(SearchQuery(last="x"), adapters=[]) == []


@pytest.mark.asyncio
async def test_search_is_audited(tmp_path):
    log = AuditLog(tmp_path / "a.sqlite")
    await _collect(SearchQuery(last="smith"), adapters=[StubAdapter("t", records=1)], audit=log)
    rows = log.recent()
    assert len(rows) == 1
    assert rows[0]["query_last"] == "smith" and rows[0]["sources"] == "t"
    log.close()
