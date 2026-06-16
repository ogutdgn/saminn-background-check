"""FastAPI app — `POST /api/search` streams one SSE event per source.

The thin HTTP boundary: validate the `SearchQuery`, write the audit entry, and stream
each `AdapterResult` from the orchestrator as it lands (`text/event-stream`). No scraping
or per-county logic here. Request/response bodies are the Pydantic contract models, so
FastAPI's generated OpenAPI schema is the source of truth for the frontend's TS types.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from adapters import registry
from adapters.base import Adapter, AdapterContext, AdapterResult, InmateRecord, SearchQuery
from core.audit import AuditLog
from core.orchestrator import _DEFAULT_TIMEOUT_S, _USER_AGENT, run_search

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "audit.sqlite"


def _db_path() -> Path:
    path = Path(os.environ.get("SAMINN_AUDIT_DB", _DEFAULT_DB))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.audit = AuditLog(_db_path())
    try:
        yield
    finally:
        app.state.audit.close()


app = FastAPI(
    title="The Samaritan Inn — Background Search",
    version="0.1.0",
    lifespan=lifespan,
)

# Dev only: the Vite dev server is a different origin. In prod the built frontend is
# served from this same origin, so this is a no-op there.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_audit(request: Request) -> AuditLog:
    return request.app.state.audit


def get_adapters() -> list[Adapter]:
    """The enabled adapters the search fans out to (overridable in tests)."""
    return registry.enabled_adapters()


@app.get("/api/health")
async def health() -> dict:
    """Liveness + the enabled sources, with enough metadata for the UI to render a card per source
    up front (its real display name, transport, whether it carries mugshots) — so the frontend needs
    no hardcoded per-source knowledge (no "Odcr County" guess, no IMAGE_SOURCES list)."""
    return {
        "status": "ok",
        "sources": [
            {
                "id": a.id,
                "display_name": a.display_name,
                "transport": a.transport,
                "has_photos": a.has_photos,
            }
            for a in registry.enabled_adapters()
        ],
    }


# Declared for the OpenAPI schema (frontend type generation) — the live route streams.
@app.post("/api/search", response_model=AdapterResult, responses={200: {"content": {"text/event-stream": {}}}})
async def search(
    query: SearchQuery,
    audit: AuditLog = Depends(get_audit),
    adapters: list[Adapter] = Depends(get_adapters),
    staff: str | None = None,
) -> EventSourceResponse:
    """Fan `query` out to the enabled sources; stream one SSE `result` event per source,
    then a final `done` event. A source that errors emits a `result` with status `error`
    — it never breaks the stream for the others."""

    async def event_stream():
        async for result in run_search(query, adapters=adapters, audit=audit, staff=staff):
            yield {"event": "result", "data": result.model_dump_json()}
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_stream())


@app.get("/api/record/{source}/{record_id}", response_model=InmateRecord)
async def record_detail(
    source: str,
    record_id: str,
    adapters: list[Adapter] = Depends(get_adapters),
) -> InmateRecord:
    """Fetch one record's full detail on demand (e.g. Tarrant CID -> mugshot + charges).

    Drives both the per-card "More details" expand and the search-time profile photo for
    image sources. The frontend merges this onto the list record it already has.
    """
    adapter = next((a for a in adapters if a.id == source), None)
    if adapter is None:
        raise HTTPException(status_code=404, detail=f"unknown or disabled source: {source}")
    # Honor the adapter's own budget (mirrors the orchestrator). A Tier-3 detail like Denton's
    # re-seeds the session (GET + 2 POSTs + GET) through Cloudflare and declares timeout_s=45 — a
    # flat 20s here was cutting that short on a slow moment -> None -> "Couldn't load the full record".
    budget = adapter.timeout_s or _DEFAULT_TIMEOUT_S
    async with httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT}, follow_redirects=True, timeout=httpx.Timeout(budget)
    ) as client:
        record = await adapter.fetch_detail(record_id, AdapterContext(client, timeout_s=budget))
    if record is None:
        raise HTTPException(status_code=404, detail="no detail available for this record")
    return record
