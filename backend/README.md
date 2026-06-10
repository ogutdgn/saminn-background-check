# backend/

The Python / FastAPI engine. Everything that finds, scrapes, normalizes, caches,
and audits records lives here. No UI code.

## Layout

```
backend/
├── adapters/   # one file per source + the shared contract + the registry
├── core/       # orchestrator, browser manager, cache, audit  (the engine)
├── web/        # FastAPI app + the SSE /api/search endpoint
└── tests/      # per-adapter fixture tests
```

## Conventions

- Python 3.12+, `async`/`await`, full type hints.
- HTTP scraping via `httpx`; browser scraping via the **shared** Playwright manager
  in `core/` — never a private browser, never raw `requests`.
- Data is validated through the Pydantic contract in `adapters/base.py`.
- Files for specific counties (e.g. `adapters/collin.py`) are created **as those
  counties are built**, following `docs/ADDING_A_SOURCE.md`. They do not exist up
  front.

## Project tooling (set up in Phase 1, not yet present)

- Dependency/venv management (e.g. `uv` or `poetry`) and a `pyproject.toml`.
- `pytest` for the test suite.
- These are created in the first implementation phase; this skeleton is docs-only
  for now.
