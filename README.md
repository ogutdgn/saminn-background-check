# saminn-background-check

Open-source tool built for **The Samaritan Inn** that streamlines background checks
for homeless shelters and nonprofits by unifying public court / jail record searches
across Texas (and select Oklahoma) counties.

A staff member types **one name** at intake. The tool searches several county
court & jail systems in parallel and streams a normalized result per source into
one screen, so the intake worker doesn't have to visit and learn seven different
government websites.

> ⚠️ This tool handles **PII and criminal-record data about vulnerable people**.
> Read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §"Responsible-use rules"
> before contributing. Name-based record matching is error-prone — the tool
> **surfaces possible matches for a human to review; it never decides anything.**

---

## What this is (and isn't)

- **Is:** a read-only aggregator of *already-public* government records, run
  in-house, with an audit trail of who searched what.
- **Isn't:** a credit/criminal-decision engine, a bulk-scraper, or anything that
  defeats CAPTCHAs or accesses non-public data. See the rules in the architecture doc.

## Tech stack (at a glance)

| Layer | Choice |
| --- | --- |
| Runs on | An **on-premise always-on server** on the shelter's network (not cloud) |
| Backend | **Python 3.12+ / FastAPI** (async, Server-Sent Events streaming) |
| HTTP scraping | **httpx** (async) + **selectolax** / BeautifulSoup |
| Browser scraping | **Playwright (Python)** — only for sources that require it |
| Frontend | **React (Vite + TypeScript)** + a component library, talking to the API over SSE |
| Storage | **SQLite** — result cache (TTL) + access audit log |
| Shared contract | **Pydantic** `InmateRecord` / `AdapterResult` models |

Full rationale: [`docs/TECH_STACK.md`](docs/TECH_STACK.md).

## Documentation map

Start here, in order:

1. [`CLAUDE.md`](CLAUDE.md) — how to work in this repo (with or without Claude Code).
2. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the layers, the data flow, the contract.
3. [`docs/TECH_STACK.md`](docs/TECH_STACK.md) — what we chose and why; what's still open.
4. [`docs/SOURCES.md`](docs/SOURCES.md) — every target source, its tier, and its status.
5. [`docs/ADDING_A_SOURCE.md`](docs/ADDING_A_SOURCE.md) — **the pipeline** for adding a
   new county, with review gates. Read this before you take a county.

## Project layout

```
saminn-background-check/
├── docs/            # architecture, stack, sources, the add-a-source pipeline
├── backend/         # Python / FastAPI engine
│   ├── adapters/    # one file per source (created as each county is built)
│   ├── core/        # orchestrator, browser manager, cache, audit
│   ├── web/         # FastAPI app + SSE endpoint
│   └── tests/       # per-adapter fixture tests
├── frontend/        # React (Vite) UI
└── .claude/         # repo-local skills (commit style, etc.)
```

Files like `backend/adapters/collin.py` **do not exist yet** — they are created
phase by phase as each county is implemented, following the pipeline doc.

## Status

🚧 **Foundation phase.** Architecture, stack, and the source map are decided and
documented. Implementation begins county by county. See `docs/SOURCES.md` for the
current build status of each source.
