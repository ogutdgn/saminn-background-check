# Working in this repo

This file orients anyone — teammate or Claude Code — who opens this project. Read
it first. It is short on purpose; the detail lives in `docs/`.

## What we're building

A single-name background search that fans out to several Texas/Oklahoma county
court & jail systems and streams a normalized result per source. Built for The
Samaritan Inn's intake process. See [`README.md`](README.md) and
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## The one rule that makes the team scale

**Every source is an independent "adapter" behind a shared contract.** One file
per county. Adapters never import each other. They all return the same Pydantic
shape (`InmateRecord` / `AdapterResult`). This is what lets five people work on
five counties at once without colliding. Do not break this pattern.

If you are about to write code that makes one adapter depend on another, or that
puts scraping logic outside an adapter, stop — you are working against the
architecture. Re-read `docs/ARCHITECTURE.md`.

## Before you start a task

1. **Taking a county?** Read [`docs/ADDING_A_SOURCE.md`](docs/ADDING_A_SOURCE.md)
   in full. It is a 5-stage pipeline with review gates. Do not skip to writing
   the adapter — Stage 0 (recon) and Stage 1 (raw data-pull spike) come first and
   are reviewed by the lead before any adapter code.
2. **Check the source's status** in [`docs/SOURCES.md`](docs/SOURCES.md) — it may
   already be classified, or known-blocked.
3. **Work on a branch**, never directly on `main`. Branch name:
   `source/<county>` for a new source, `core/<thing>` for engine work,
   `frontend/<thing>` for UI.

## Conventions

- **Backend:** Python 3.12+, `async`/`await`, type hints everywhere. Adapters use
  `httpx` (HTTP sources) or the shared Playwright manager (browser sources) — never
  raw `requests` or a private browser instance.
- **The contract is law.** If you think `InmateRecord` needs a new field, that is a
  conversation with the lead and a change to one file that everyone depends on —
  not something you add quietly in your adapter.
- **Frontend:** React + TypeScript. The UI only renders what the API streams; it
  contains no scraping logic and no per-county special-casing beyond display.
- **Tests:** every adapter ships with a fixture-based test (a captured real
  response) so we can run the suite without hitting live sites. See
  `backend/tests/`.

## Responsible-use rules (non-negotiable)

These are summarized here and stated in full in `docs/ARCHITECTURE.md`:

- Only **public** records, only **single-name** intake searches — no bulk scraping.
- **No CAPTCHA-defeating** services or stealth circumvention of a security wall.
  If a source is behind a server-side CAPTCHA/WAF, it is out of scope — find a
  different public door or leave it disabled. (See the source tiers.)
- Every search is **audit-logged** (who, what name, when).
- Results are **possible matches for human review**, never automated decisions.

## Commit style

Follow `.claude/skills/commit-style/SKILL.md`. In short: `<type>(<scope>): summary`,
always a body (what + why), stage files by path (never `git add .`), branch then PR
for anything touching the contract, the orchestrator, or 5+ files.

## Where things are

| You want to… | Go to |
| --- | --- |
| Understand the system | `docs/ARCHITECTURE.md` |
| Know why we chose the stack | `docs/TECH_STACK.md` |
| See all sources + their status | `docs/SOURCES.md` |
| Add a new county | `docs/ADDING_A_SOURCE.md` |
| Write an adapter | `backend/adapters/README.md` |
| Touch the engine | `backend/core/README.md` |
| Work on the API | `backend/web/README.md` |
| Work on the UI | `frontend/README.md` |
