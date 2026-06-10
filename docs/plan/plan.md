# Plan — saminn-background-check

> The **general, agreed plan**. Stable; changes only when the strategy itself changes.
> Companion docs: [execution-map.md](execution-map.md) (what to do in a session) ·
> [last-point.md](last-point.md) (exact current state).
> Reference: [../ARCHITECTURE.md](../ARCHITECTURE.md) · [../TECH_STACK.md](../TECH_STACK.md) ·
> [../SOURCES.md](../SOURCES.md) · [../ADDING_A_SOURCE.md](../ADDING_A_SOURCE.md).

## Goal
A single-name background search for The Samaritan Inn's intake: type one name, fan out to
several Texas/Oklahoma county court & jail systems in parallel, and stream a normalized result
per source into one screen — so intake staff don't have to visit and learn seven government
websites. Read-only, public records, audit-logged, human-reviewed.

## Locked architecture & stack (see the reference docs for full detail)
- **Runs on an on-premise always-on server** on the shelter's network (not cloud) — the only
  place that can run a browser for browser-only sources and keeps PII in-building. (TECH_STACK.md)
- **Backend:** Python 3.12+ / FastAPI, async, **SSE streaming**. **Frontend:** React (Vite + TS)
  over SSE. **Storage:** SQLite (cache + audit). (TECH_STACK.md)
- **Core pattern:** one **adapter per source** behind a shared **Pydantic contract**
  (`InmateRecord` / `AdapterResult`), a **registry**, and a central **orchestrator** that fans
  out, isolates failures, and streams each result as it lands. (ARCHITECTURE.md)
- **Sources are tiered** by their easiest open public door (1 API → 5 blocked/out-of-scope). Six
  proven reachable; Fannin a stretch. (SOURCES.md)

## The hard constraints (never violate)
1. **Responsible use:** public records only, single-name searches only, **no defeating
   server-side CAPTCHAs/WAFs**, audit everything, **human-in-the-loop** (the tool surfaces
   possible matches; it never decides). Full text in ARCHITECTURE.md.
2. **The contract is law:** every adapter returns the same shape; changing `base.py` is a
   reviewed, lead-level change because everyone depends on it.
3. **Source isolation:** adapters never import each other; one failing source never breaks others.

## Development process (how we work)
- **Foundation first, then sources one at a time.** Foundational decisions are locked (this doc +
  the reference docs). Each county is built **on its own branch via the add-a-source pipeline**,
  against real probed endpoints — not designed up front on paper.
- **The add-a-source pipeline** ([../ADDING_A_SOURCE.md](../ADDING_A_SOURCE.md)) is 5 stages with
  **review gates**: Recon → Data-pull spike → Adapter → Tests & fixtures → Integrate & enable.
  The lead holds the gates. This is how "person A takes Collin, person B takes Dallas" stays
  consistent and reviewed.
- **Each source/subsystem branch:** build → pass the gate (Adapter checklist + fixture tests) →
  **update the plan docs via the `plan-tracking` skill** → PR for review.
- **Files are created phase by phase**, not up front — `adapters/collin.py` exists only once
  Collin is built.

## Branching model
- **Never do code work on `main`.** Always **create + checkout a branch first**
  (verify with `git branch --show-current` before editing).
- `main` — stable; receives **only reviewed PR merges at coherent milestones**.
- Branch naming: `source/<county>` (a new source), `core/<thing>` (engine), `api/<thing>`,
  `frontend/<thing>`, `docs/<thing>`.

## Phase roadmap
(Order may adjust; sources within Phase 2 can be built in parallel by different people.)

| Phase | What | Status |
|------|------|--------|
| **0** | Foundation: decide deployment + stack + architecture; recon & tier the sources; write the docs + the add-a-source pipeline + plan-tracking | ✅ done |
| **1** | Scaffold: backend project (deps/pyproject), the **contract** (`adapters/base.py`) + `registry`, the **orchestrator** + **browser manager** + **cache** + **audit**, the FastAPI **`/api/search` SSE** endpoint, the React/Vite frontend with an SSE client + one source card. Prove one **end-to-end vertical slice** with a stub adapter. | |
| **2** | **Sources, county by county via the pipeline:** Tarrant (T1) · Dallas/Hunt/ODCR (T2) · Denton (T3) · Collin (T4) · Fannin (stretch). | |
| **3** | Frontend: full record rendering (charges, mugshots, `matched_on` filter), mark-relevant, **export report** for the intake file. | |
| **4** | Hardening + go-live: **auth decision** + audit-log review, browser rate-limit tuning, deploy as a **systemd service / Docker** on the on-prem box. | |

## Team division
Who owns which lane (adapters by tier, core/browser, API, frontend, recon) is tracked in the
team-division doc (written separately) and reflected in `last-point.md` as assignments change.

## Pointers
- Architecture / data flow / contract: [../ARCHITECTURE.md](../ARCHITECTURE.md)
- Stack decisions (locked + deferred): [../TECH_STACK.md](../TECH_STACK.md)
- Sources, tiers, status: [../SOURCES.md](../SOURCES.md)
- The add-a-source pipeline: [../ADDING_A_SOURCE.md](../ADDING_A_SOURCE.md)
- How to work in the repo: [../../CLAUDE.md](../../CLAUDE.md)
