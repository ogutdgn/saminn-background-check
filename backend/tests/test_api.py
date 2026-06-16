"""API — POST /api/search streams SSE events; GET /api/health.

Runs the ASGI app in-process via httpx ASGITransport with stub adapters injected (no
live calls). An autouse fixture overrides the audit dependency with a temp DB, so the
tests don't depend on the lifespan (ASGITransport doesn't run it).
"""
import json

import httpx
import pytest

from adapters.base import Adapter, AdapterResult, AdapterStatus, InmateRecord, SearchQuery
from core.audit import AuditLog
from web.app import app, get_adapters, get_audit


class ApiStub(Adapter):
    transport = "http"
    tier = 1

    def __init__(self, id, *, status=AdapterStatus.OK, records=0):
        self.id = id
        self.display_name = id.title()
        self._status = status
        self._records = records

    async def search(self, query: SearchQuery, ctx) -> AdapterResult:
        recs = [InmateRecord(source=self.id, name=f"{query.last.upper()} {i}") for i in range(self._records)]
        return AdapterResult(
            source=self.id,
            display_name=self.display_name,
            status=self._status,
            records=recs,
            total=self._records or None,
            duration_ms=1,
        )


def _parse_sse(text: str) -> list[tuple[str, str]]:
    """Return [(event, data), ...] from a raw SSE body."""
    events, cur = [], None
    for line in text.splitlines():
        if line.startswith("event:"):
            cur = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            events.append((cur, line.split(":", 1)[1].strip()))
    return events


@pytest.fixture(autouse=True)
def api_audit(tmp_path):
    audit = AuditLog(tmp_path / "audit.sqlite")
    app.dependency_overrides[get_audit] = lambda: audit
    yield audit
    app.dependency_overrides.clear()
    audit.close()


async def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_health_lists_enabled_sources():
    async with await _client() as ac:
        r = await ac.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    # sources carry the metadata the UI renders cards from (id, display name, photo capability)
    by_id = {s["id"]: s for s in body["sources"]}
    assert "tarrant" in by_id and "dallas" in by_id        # enabled (Stage 4)
    assert by_id["tarrant"]["display_name"] == "Tarrant County"
    assert by_id["tarrant"]["has_photos"] is True          # jail roster -> mugshots
    assert by_id["dallas"]["has_photos"] is False          # court records -> no mugshots
    # every source exposes a public portal URL so the UI can always offer a navigable source link
    # (even when a record has no per-record deep link); the frontend hardcodes no per-source URLs.
    assert all(s.get("portal_url", "").startswith("https://") for s in body["sources"])


@pytest.mark.asyncio
async def test_search_streams_one_event_per_source_then_done(api_audit):
    app.dependency_overrides[get_adapters] = lambda: [
        ApiStub("tarrant", records=2),
        ApiStub("dallas", status=AdapterStatus.NO_RESULTS),
    ]
    async with await _client() as ac:
        async with ac.stream("POST", "/api/search", json={"last": "smith"}) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            body = "".join([chunk async for chunk in resp.aiter_text()])

    events = _parse_sse(body)
    kinds = [e[0] for e in events]
    assert kinds.count("result") == 2          # one per source
    assert kinds[-1] == "done"

    results = {json.loads(d)["source"]: json.loads(d) for k, d in events if k == "result"}
    assert results["tarrant"]["status"] == "ok" and len(results["tarrant"]["records"]) == 2
    assert results["dallas"]["status"] == "no_results"
    assert api_audit.recent()[0]["query_last"] == "smith"   # search was audited


@pytest.mark.asyncio
async def test_search_validates_body():
    # `last` is required by the contract -> 422 without it
    async with await _client() as ac:
        r = await ac.post("/api/search", json={"first": "john"})
    assert r.status_code == 422


class DetailStub(ApiStub):
    async def fetch_detail(self, record_id, ctx):
        return InmateRecord(source=self.id, name="", photo_base64="/9j/abc", raw={"CID": record_id})


@pytest.mark.asyncio
async def test_record_detail_returns_hydrated_record():
    app.dependency_overrides[get_adapters] = lambda: [DetailStub("tarrant")]
    async with await _client() as ac:
        r = await ac.get("/api/record/tarrant/1042590")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "tarrant"
    assert body["photo_base64"] == "/9j/abc"
    assert body["raw"]["CID"] == "1042590"


@pytest.mark.asyncio
async def test_record_detail_unknown_source_404():
    app.dependency_overrides[get_adapters] = lambda: []
    async with await _client() as ac:
        r = await ac.get("/api/record/nope/123")
    assert r.status_code == 404
