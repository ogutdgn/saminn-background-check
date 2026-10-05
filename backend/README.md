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

## Install (server or dev machine)

Install from the pinned `requirements.txt`, not from a hand-written package list —
unpinned installs have already broken twice (a missing package, then a breaking
`selectolax` 1.0 release).

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest tests/                      # expect: all pass, 5 skipped on a fresh clone
```

The 5 skipped test files need captured fixtures that contain real PII and are
git-ignored, so they only run on a machine that has them.

`playwright install chromium` is only needed if a browser-tier source (Collin) is
enabled; it is disabled by default.

To change dependencies: edit `pyproject.toml`, then regenerate the pins with
`uv pip compile pyproject.toml --extra dev --universal --python-version 3.12 -o requirements.txt`.
