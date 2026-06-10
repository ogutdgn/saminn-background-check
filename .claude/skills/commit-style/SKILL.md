---
name: commit-style
description: Use before any git commit in saminn-background-check. Defines subject-line scope tags, body detail requirements, staging discipline, and PR-vs-direct-commit guidance.
---

# Commit Style (saminn-background-check)

## Subject line

Format: `<type>(<scope>): <imperative summary>`

`<scope>` is one of:
- A **source id** — `tarrant`, `dallas`, `hunt`, `denton`, `collin`, `odcr`,
  `fannin`, … — for work on a specific county adapter.
- `adapters` — the adapter layer in general, or the `registry`.
- `contract` — `adapters/base.py` and the Pydantic models / TS types. **Load-bearing:
  everyone depends on it.**
- `core` — engine in general; or a specific subsystem: `orchestrator`, `browser`,
  `cache`, `audit`.
- `api` — the FastAPI app / endpoints (`backend/web/`).
- `frontend` — the React UI.
- `sources` — recon / classification updates to `SOURCES.md`.
- `test` — fixtures / test harness only.
- `docs`, `skills`, `repo` — documentation, repo-local skills, or cross-cutting / root changes.
- `restructure` — large structural changes (rare).

`<type>` is one of:
- `feat` — new user-visible feature or capability.
- `fix` — bug fix (subject names the bug, not the solution).
- `recon` — Stage 0 source-discovery findings (a door classified, a tier assigned).
- `refactor` — internal restructure with no behaviour change.
- `ui` — visual-only change (no logic).
- `docs` — documentation only.
- `test` — fixtures or test scripts only.
- `chore` — tooling, deps, config.

Imperative form, lowercase first word. Keep under 72 chars.

## Body — required for all non-trivial commits

Always include a body. One blank line after the subject, then:

**What changed** — bullet list of concrete changes (files / components / behaviour).
Be specific: name the adapter, function, or file touched.

**Why** — one or two sentences. What problem does this solve, or what goal does it serve?

**Impact notes** (include when relevant):
- `Source: <county> · tier <n> · transport <http|browser>` — when adding/altering a source.
- `Pipeline stage: <0-4>` — which stage of `docs/ADDING_A_SOURCE.md` this completes.
- `Tests: N pass / 0 fail` — when the suite was run.
- `Contract change` — if `InmateRecord` / `AdapterResult` changed (everyone is affected).
- `Breaking: <what>` — if an API or data-shape contract changed.

## Trailer

**Do NOT add `Co-Authored-By: Claude` or any AI authorship trailer.** Never.

## Staging

- Stage files explicitly by path — never `git add .` or `git add -A`.
- Run `git diff --cached --stat` before committing to verify the staged set.
- Never commit: `__pycache__/`, `node_modules/`, `dist/`, `build/`, `*.sqlite`,
  `.env`, captured fixtures containing PII, `*.log`, `.DS_Store`.

## When to PR vs commit direct to branch

- **Direct commit**: single-concern change on a feature branch, already reviewed in
  conversation.
- **PR (required)**: anything touching `adapters/base.py` (the contract), the
  orchestrator/browser manager, the audit log, or 5+ files — so it can be reviewed
  before merging to `main`. New sources merge to `main` via PR at Stage 4.
- Work on a branch, never directly on `main`. Branch names: `source/<county>`,
  `core/<thing>`, `frontend/<thing>`, `docs/<thing>`.
- Force-push only on your own branch, never on `main`.

## What NOT to do

- Skip hooks (`--no-verify`) — investigate the failing hook.
- Amend a published commit.
- Lump unrelated changes into one commit.
- Change the shared contract quietly inside an adapter commit — that's its own
  reviewed `contract` change.
