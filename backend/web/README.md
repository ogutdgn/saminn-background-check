# backend/web/

The FastAPI application — the thin HTTP boundary between the React frontend and the
engine. It contains **no scraping logic**; it validates input, streams results, and
records the audit entry.

## What lives here (created in Phase 1)

| File | Purpose |
| --- | --- |
| `app.py` | The FastAPI app and routes. The main one is `POST /api/search`, which validates the query, writes an audit entry, and returns a **Server-Sent Events** stream — one event per source `AdapterResult` as the orchestrator yields it. |

## Conventions

- Request/response bodies are the Pydantic models from `adapters/base.py`, so the
  API schema and the data contract are the same thing.
- FastAPI's generated **OpenAPI schema** is the source of truth for the frontend's
  TypeScript types — generate them from it so they never drift.
- Keep endpoints dumb: parse/validate → call the orchestrator → stream. No
  per-county branching here.

## Streaming shape

`POST /api/search` → `text/event-stream`. Each event carries one `AdapterResult`
(`status`, `records`, `error`, `duration_ms`). The frontend renders/updates the
matching source card as each event arrives. A source that errors emits an event
with `status: "error"` — it never breaks the stream for the others.

## Prod note

In production the built React static files are served by FastAPI (or nginx in
front), so staff hit one URL on the on-prem box. In dev, the frontend runs its own
Vite server and proxies `/api` here.
