# Execution Map — session playbook + daily work log

> How to orient, execute the current phase, and record what got done. The forward plan lives
> here; the **Daily work log** (below) records what we actually did each day, with checkboxes.
> Big picture: [plan.md](plan.md) · dated state snapshots: [last-point.md](last-point.md).
> Renewed via the `plan-tracking` skill.

## At session START (always, in order)
1. Read **[last-point.md](last-point.md)** (top entry) — where we left off, current branch, next.
2. Read **this file** — current phase, next actions, and the Daily work log.
3. Skim **[plan.md](plan.md)** — goal, locked architecture/stack, the hard constraints, dev process.
4. If you're taking a county, read **[../ADDING_A_SOURCE.md](../ADDING_A_SOURCE.md)** (the pipeline)
   and the source's row in **[../SOURCES.md](../SOURCES.md)**.

> ⚠️ **Branching rule — never do code work on `main`.** Before writing or committing any code,
> **create and checkout a fresh branch** (`source/<county>`, `core/<thing>`, `frontend/<thing>`,
> `docs/<thing>`). Confirm first with `git branch --show-current`. `main` receives **only reviewed
> PR merges at stable milestones**.

## How to execute a SOURCE (the add-a-source loop)
1. **Create + checkout** `source/<county>`. Verify with `git branch --show-current`.
2. **Stage 0 — Recon:** find every public door, classify the tier, update SOURCES.md. **Gate: lead OKs the door + tier.**
3. **Stage 1 — Data-pull spike:** prove the raw pull (curl/script), capture a fixture. **Gate: lead OKs the raw pull + fixture.**
4. **Stage 2 — Adapter:** implement `adapters/<county>.py` against the contract; register disabled. **Gate: code review vs the Adapter checklist.**
5. **Stage 3 — Tests & fixtures:** fixture-based test (multi-result + no-results + matched_on). **Gate: tests pass.**
6. **Stage 4 — Integrate & enable:** flip enabled, verify end-to-end in the UI, set status `done` in SOURCES.md. **Gate: lead verifies, PR merges.**
7. **Checkpoint** (via `plan-tracking`): append a dated entry to last-point.md + tick the Daily work log.

## How to execute a SUBSYSTEM (core / api / frontend)
1. **Create + checkout** the branch.
2. Build against the contract; keep the engine source-agnostic (no county names in `core/`).
3. Add tests; keep the suite green.
4. **Checkpoint** via `plan-tracking`; PR for review.

## CURRENT PHASE → Phase 1: Scaffold (in progress)
> **Phase 0 is DONE.** Deployment, stack, and architecture decided; sources reconned + tiered;
> the add-a-source pipeline + plan-tracking in place. (2026-06-10 entry in [last-point.md](last-point.md).)
>
> **Phase 1 (Scaffold) — progress (2026-06-14):**
> - [x] Backend project setup (`.venv`, `pyproject.toml`, `pytest`).
> - [x] **The contract:** `backend/adapters/base.py` (InmateRecord/AdapterResult/Adapter + structured `SearchQuery`) + `registry.py`. **Locked v1 — validated against two real sources.**
> - [x] **First two adapters early** (we pulled raw first): `tarrant.py` + `dallas.py`, fixture-tested, adversarially verified, registered **disabled**. (Stage 2–3.)
> - [ ] **Core engine:** `orchestrator.py` (fan-out + SSE-yield + timeout/isolation) + `audit.py`. (`browser.py`, `cache.py` deferred until a source needs them.)
> - [ ] **API:** `backend/web/app.py` with `POST /api/search` SSE.
> - [ ] **Frontend:** Vite + TS scaffold, SSE client, one source card; types from OpenAPI.
> - [ ] **Vertical slice:** search → orchestrator → SSE → card, end-to-end (using the real Tarrant/Dallas adapters).
>
> **Loose ends:** sync `ARCHITECTURE.md` contract spec to the structured `SearchQuery`; Dallas
> pagination is a Stage-4 blocker. Team-size question resolved: **solo** (no team-division doc).

## Daily work log

### 2026-06-14
- [x] Stage-1 raw pulls (live): **Tarrant** (JSON jTable, 3-call flow + base64 mugshot) and **Dallas** (HTML court search, disclaimer gate, dispositions, no mugshots). Fixtures + spike notes committed.
- [x] Locked the **v1 contract** (`base.py`) with a **structured `SearchQuery`**; registry + sanity tests. Committed.
- [x] Built + fixture-tested **Tarrant** and **Dallas** adapters (Stage 2–3); registered disabled.
- [x] **Adversarial verification workflow** (3 agents) — caught + fixed a real Dallas grouping bug (masked-DOB merge/split → one record per case-row), `total=None`, Tarrant sex→None. 19 tests pass. Committed.
- [x] Carried over from 06-10: team size **resolved (solo)** → team-division doc dropped; foundation + plan docs committed.
- [ ] Orchestrator + audit log → API SSE → frontend card → vertical slice.
- [ ] Sync `ARCHITECTURE.md` `SearchQuery`; resolve Dallas pagination (Stage-4 blocker).

### 2026-06-10
- [x] Reviewed the existing demo (Next.js + Python versions) and extracted the reusable **knowledge** (source tiers, per-site gotchas) rather than the code.
- [x] **Live recon** beyond the demo: proved Hunt (open Sheriff Classic-ASP roster) and Oklahoma/ODCR (open, 1000 results) are reachable — both were wrongly marked "blocked"; Fannin's CAPTCHA found to be client-side (defeatable in-rules).
- [x] **Locked foundation decisions:** on-prem server · Python/FastAPI backend · React/Vite frontend · SSE streaming · SQLite (cache + audit) · adapter+contract+orchestrator pattern.
- [x] Wrote the foundation docs: `README`, `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/TECH_STACK.md`, `docs/SOURCES.md`, `docs/ADDING_A_SOURCE.md` (the pipeline), folder-skeleton READMEs, `.gitignore`, adapted `commit-style` skill.
- [x] Added the **plan-tracking** system (`plan.md` / `execution-map.md` / `last-point.md` + skill).
- [ ] Confirm team size → write the team-division doc.
- [ ] Commit the foundation + plan docs (branch `docs/foundation`, PR).
- [ ] Begin Phase 1 scaffold (start with the contract).
