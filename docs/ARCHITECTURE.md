# Architecture

This is the master reference for how the system is built. Read it before writing
code. It is intentionally specific about the *shape* of the system and deliberately
silent about counties we haven't built yet.

## The driving principle

> **Sources fail independently, and the slow ones must never block the fast ones.**

Every government site we read is outside our control. Any of them can go down,
change a form field, or add bot-protection on any given day. Some answer in
200 ms over plain HTTP; one needs a full browser and takes several seconds. The
architecture exists to make all of that survivable and parallel.

Three consequences, baked into the design:

1. **One adapter per source, behind a shared contract.** Failures are isolated;
   teammates don't collide.
2. **Fan-out, stream as each lands.** The UI shows Tarrant's result while Collin's
   browser is still working.
3. **Everything is replayable offline.** Each adapter ships a captured fixture, so
   we can develop and test without hammering live sites.

## The layers

```
┌──────────────────────────────────────────────────────────────┐
│  STAFF BROWSER  →  internal URL on the on-prem server          │
└───────────────────────────────┬──────────────────────────────┘
                                │  type a name, watch results stream in
┌───────────────────────────────▼──────────────────────────────┐
│  FRONTEND  (React + Vite)                  frontend/           │
│  search box · per-source result cards · mark-relevant · export │
│  Dumb on purpose: only renders what the API streams.           │
└───────────────────────────────┬──────────────────────────────┘
                                │  POST /api/search  → SSE stream (one event/source)
┌───────────────────────────────▼──────────────────────────────┐
│  WEB / API  (FastAPI)                      backend/web/        │
│  validates input · opens an SSE stream · writes the audit log  │
└───────────────────────────────┬──────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────┐
│  ORCHESTRATOR  (the brain)                 backend/core/       │
│  • fan out to all ENABLED adapters concurrently                │
│  • isolate failures (one source erroring ≠ whole search fails) │
│  • per-source timeout + cancellation                           │
│  • yield each AdapterResult the moment it arrives              │
└──────┬───────────────────────────────────────┬───────────────┘
       │                                       │
┌──────▼─────────────────┐          ┌──────────▼─────────────────┐
│  HTTP ADAPTERS          │          │  BROWSER ADAPTERS           │
│  backend/adapters/*.py  │          │  backend/adapters/*.py      │
│  async httpx, run fully │          │  go through the shared      │
│  in parallel (fast lane)│          │  BROWSER MANAGER (pool +    │
│                         │          │  queue, rate-limited)       │
└──────┬──────────────────┘          └──────────┬─────────────────┘
       └──────────────────┬───────────────────┘
                          │  every adapter returns the SAME shape
              ┌───────────▼────────────┐
              │  SHARED CONTRACT        │  backend/adapters/base.py
              │  InmateRecord /          │  ← the keystone. Lock first.
              │  AdapterResult / Adapter │
              └───────────┬────────────┘
        ┌─────────────────┼──────────────────┐
┌───────▼──────┐  ┌───────▼───────┐  ┌────────▼────────┐
│  CACHE        │  │  AUDIT LOG     │  │  SOURCE REGISTRY │
│  SQLite, TTL  │  │  SQLite        │  │  enabled + tier  │
│  query+source │  │  who/what/when │  │  registry.py     │
└───────────────┘  └────────────────┘  └──────────────────┘
```

## The shared contract (the most important thing in the repo)

Every adapter returns the identical shape. This file (`backend/adapters/base.py`)
is created in the first implementation phase and changes rarely; a change to it
ripples to everyone, so it goes through the lead. The canonical spec:

```python
# backend/adapters/base.py  (spec — created in Phase 1, shown here as the contract)
from abc import ABC, abstractmethod
from enum import Enum
from pydantic import BaseModel

class MatchType(str, Enum):
    NAME = "name"          # query is in the person's real name
    ALIAS = "alias"        # matched a known alias
    ATTORNEY = "attorney"  # matched the attorney, not the defendant
    OTHER = "other"

class MatchInfo(BaseModel):
    type: MatchType
    detail: str | None = None   # e.g. "Alias: Smith, John"

class Charge(BaseModel):
    offense: str | None = None
    case_no: str | None = None
    warrant_no: str | None = None
    disposition: str | None = None
    extra: dict = {}            # source-specific fields kept verbatim

class InmateRecord(BaseModel):
    source: str                 # adapter id, e.g. "tarrant"
    source_url: str | None = None
    name: str
    year_of_birth: str | None = None
    sex: str | None = None
    booking_date: str | None = None
    photo_base64: str | None = None
    charges: list[Charge] = []
    matched_on: list[MatchInfo] = []   # WHY this row matched the query
    raw: dict = {}              # everything as scraped, for debugging/audit

class AdapterStatus(str, Enum):
    OK = "ok"
    NO_RESULTS = "no_results"
    ERROR = "error"
    TIMEOUT = "timeout"

class AdapterResult(BaseModel):
    source: str
    display_name: str
    status: AdapterStatus
    records: list[InmateRecord] = []
    total: int | None = None
    duration_ms: int
    error: str | None = None

class SearchQuery(BaseModel):
    name: str
    max_results: int = 25

class Adapter(ABC):
    id: str                     # "tarrant"
    display_name: str           # "Tarrant County"
    transport: str              # "http" | "browser"
    tier: int                   # 1..5, see SOURCES.md

    @abstractmethod
    async def search(self, query: SearchQuery, ctx: "AdapterContext") -> AdapterResult:
        ...
```

The frontend mirrors `InmateRecord` / `AdapterResult` as TypeScript types,
ideally generated from FastAPI's OpenAPI schema so they never drift.

### Why `matched_on` matters

A search for "John Smith" returns the *defendant* John Smith, but also rows where
John Smith is the *attorney*, or an *alias*. Each adapter must tag **why** a row
matched so the UI can default to showing real-name matches and hide the noise.
Getting this right per source is part of the adapter's job, not the UI's.

## The data flow of one search

1. Staff submits a name → `POST /api/search`.
2. FastAPI validates it, writes an **audit entry**, opens an **SSE stream**.
3. The **orchestrator** asks the **registry** for enabled adapters and launches
   them concurrently. HTTP adapters fire immediately; browser adapters queue
   behind the **browser manager**.
4. Each adapter checks the **cache** first (fresh hit → return it), otherwise
   pulls live, normalizes to `InmateRecord`s, returns an `AdapterResult`.
5. The orchestrator **streams each result to the UI the moment it arrives** —
   no waiting for the slowest source.
6. The UI renders a card per source, with status (ok / no results / error / still
   running), and lets staff mark records relevant and export a report.

## Components, and who tends to own them

| Component | Path | Changes how often | Typical owner |
| --- | --- | --- | --- |
| Shared contract | `backend/adapters/base.py` | Rarely | Lead |
| Orchestrator | `backend/core/orchestrator.py` | Rarely | Senior |
| Browser manager | `backend/core/browser.py` | Rarely | Senior |
| Cache | `backend/core/cache.py` | Rarely | Senior |
| Audit log | `backend/core/audit.py` | Rarely | Senior |
| Source registry | `backend/adapters/registry.py` | Per new source (one line) | Whoever adds the source |
| An adapter | `backend/adapters/<county>.py` | Independently | One person per county |
| API endpoint | `backend/web/app.py` | Rarely | Lead / backend |
| Frontend | `frontend/` | Continuously | Frontend owner |

(Exact people are assigned in the team-division doc, written separately.)

## The hard part: the browser manager

HTTP adapters are easy — concurrent `fetch`-style calls. The only real engineering
risk is the **browser**, and it is harder on a shared server than on a laptop
because **multiple staff may search at once.** Design:

- A **single shared Playwright browser**, a **small pool of contexts**, and a
  **job queue** in front of the browser-only adapters.
- HTTP adapters **bypass the queue entirely** (fast lane).
- The browser lane is **rate-limited** so we don't trip Incapsula-style protection
  on the sites that have it.

This is documented in detail in `backend/core/README.md` once built.

## Storage: SQLite, two uses

- **Cache** — keyed by `(adapter_id, normalized_query)`, with a TTL. Avoids
  re-hammering a site for the same name within a short window.
- **Audit log** — append-only: timestamp, staff identity, query, which sources ran,
  counts returned. Required because this is criminal-record PII. **Never** purged
  casually.

One file, no DB server, safe for concurrent staff. Lives on the on-prem box.

## Responsible-use rules (full text)

This tool exists to make *already-public* records easier for a shelter to check at
intake. It must stay inside these lines:

1. **Public records only.** No login-walled, paid, or non-public data.
2. **Single-name intake searches only.** No alphabet sweeps, no bulk harvesting,
   no building a database of everyone.
3. **No defeating security controls.** We do **not** use CAPTCHA-solving services,
   stealth WAF-evasion, or residential-proxy laundering to get past a server-side
   block. If a source's *only* door is behind such a wall, that source is **out of
   scope** until a legitimate public door is found (see source tiers). Reading an
   open Sheriff roster is fine; circumventing an AWS WAF is not.
4. **Respectful rate.** Human-paced, one search at a time per source; preserve the
   waits that keep us from looking like an attack.
5. **Audit everything.** Every search is logged.
6. **Human-in-the-loop.** Output is *possible matches for a person to review.* The
   tool never auto-accepts, auto-rejects, or scores an applicant. Name matching is
   error-prone (the wrong "John Smith") and a false positive could wrongly deny
   someone shelter — so a human always confirms identity against more than a name.

If a task seems to require crossing one of these lines, it is a conversation with
the lead, not a workaround.
