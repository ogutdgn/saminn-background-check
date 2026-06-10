# backend/core/

The engine. Source-agnostic machinery that every adapter relies on. This code
changes rarely and is typically owned by a senior — a change here affects every
source, so treat it as load-bearing.

## What lives here (created in Phase 1)

| File | Purpose |
| --- | --- |
| `orchestrator.py` | Takes a query, fans out to all **enabled** adapters concurrently, isolates failures, enforces per-source timeouts, and **yields each `AdapterResult` the moment it lands** (drives the SSE stream). |
| `browser.py` | The **shared** Playwright manager: a single browser, a small pool of contexts, and a job queue in front of the browser-only adapters, rate-limited so we don't trip bot-protection. HTTP adapters bypass it entirely. |
| `cache.py` | SQLite result cache keyed by `(adapter_id, normalized_query)` with a TTL. |
| `audit.py` | SQLite append-only audit log: who searched what name, when, which sources ran, counts returned. Required for PII accountability. |

## Why the browser manager is the hard part

On a shared server, multiple staff may search at once. A naïve "new browser per
search" approach would spawn many heavy Chromium processes and get the protected
sources flagged. The manager exists to **share one browser**, **bound concurrency**,
and **rate-limit the browser lane** while letting the fast HTTP lane run free. See
`docs/ARCHITECTURE.md` §"The hard part".

## Rules

- The engine knows nothing about specific counties. No county names hard-coded here.
- Adapters depend on `core`; `core` never depends on a specific adapter.
