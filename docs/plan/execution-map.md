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

## CURRENT PHASE → Phase 2: Sources (in progress) — 2 of ~6 live
> **Phase 0 ✅** and **Phase 1 ✅** (the vertical slice runs end to end). Dated entries in [last-point.md](last-point.md).
>
> **Phase 1 (Scaffold) — core COMPLETE; 2 infra pieces deferred *by design* (not unfinished):**
> - [x] Backend setup · **contract** (`base.py`, structured `SearchQuery`) + registry · **orchestrator** (fan-out/stream/timeout/isolation) · **audit** (append-only SQLite) · **API** (`/api/search` SSE, `/api/health`, `/api/record/{source}/{id}`) · **frontend** (React/Tailwind/shadcn, OpenAPI-typed) · live vertical slice.
> - [ ] `browser.py` (Playwright manager) — **deferred to Collin** (build when the first browser source lands).
> - [ ] `cache.py` (SQLite TTL) — **deferred to Phase 4** (a volume optimization; unneeded at current volume).
>
> **Phase 2 (Sources) — in progress:**
> - [x] Tarrant (T1, http) · [x] Dallas (T2, http) — both live, with photos / case-sheet detail-on-demand.
> - [ ] Hunt (T2) · [ ] ODCR (T2, OK statewide) · [ ] Denton (T3) · [ ] Collin (T4, browser — build `browser.py`) · [ ] Fannin (stretch).
>
> **Loose ends:** [x] `ARCHITECTURE.md` contract synced (2026-06-15). Open: tune Dallas paging latency
> (~18 s); tighten the Dallas name/DOB parser; replace the frontend `IMAGE_SOURCES` hardcode with a
> backend photo-capability flag; checkpoint-merge the branch to `main`. Team: **solo**.

## Daily work log

### 2026-06-15
- [x] **On-demand record detail:** `GET /api/record/{source}/{id}` + optional `Adapter.fetch_detail`. Tarrant: CID → mugshot + charges. **Dallas: Search-by-Case (stable case#) → full court case sheet** (richer than the list — full name, unmasked DOB).
- [x] **Frontend detail UX:** profile photos auto-loaded at search for image sources (capped/bounded); every record has **"More details" → popup (Dialog)**: Tarrant = big mugshot + charges, Dallas = document-styled case sheet (Courier, fixed-width columns, header bar).
- [x] **UI polish:** "No image" placeholders, search + popup **loading spinners**, wider/taller popup so the case sheet fits.
- [x] **Robustness:** `AdapterResult.partial` + Dallas time-budgeted pagination (no more timeout→0); detail fetch timeout + Retry; 60s dev-proxy timeout (Dallas detail is ~5–15s server-side). **38 tests pass.**
- [x] **Cleanup:** synced `ARCHITECTURE.md` contract spec (structured `SearchQuery`, `partial`, `fetch_detail`); clarified Phase-1 deferral (browser/cache).
- [ ] Open: Dallas latency tuning · Dallas name/DOB parser · `IMAGE_SOURCES`→backend flag · merge branch to `main` · **next source (ODCR/Hunt)**.

### 2026-06-14
- [x] Stage-1 raw pulls (live): **Tarrant** (JSON jTable, 3-call flow + base64 mugshot) and **Dallas** (HTML court search, disclaimer gate, dispositions, no mugshots). Fixtures + spike notes committed.
- [x] Locked the **v1 contract** (`base.py`) with a **structured `SearchQuery`**; registry + sanity tests. Committed.
- [x] Built + fixture-tested **Tarrant** and **Dallas** adapters (Stage 2–3); registered disabled.
- [x] **Adversarial verification workflow** (3 agents) — caught + fixed a real Dallas grouping bug (masked-DOB merge/split → one record per case-row), `total=None`, Tarrant sex→None. 19 tests pass. Committed.
- [x] Carried over from 06-10: team size **resolved (solo)** → team-division doc dropped; foundation + plan docs committed.
- [x] **Core engine:** orchestrator (fan-out, completion-order streaming, hard timeout, failure isolation) + append-only audit log. Stub-adapter tests.
- [x] **Dallas pagination solved** — `POST /paging` (`which=down`) + dedup, verified live (3-page SMITH) and against the prior demo's `dallas.ts`. **28 tests pass.**
- [x] **API:** FastAPI `POST /api/search` SSE + `/api/health`; audit wired; enabled Tarrant + Dallas (Stage 4). 31 tests.
- [x] **Frontend:** Vite + React + TS + Tailwind + shadcn/ui; SSE-over-fetch client (CRLF-tolerant); SourceCard; OpenAPI-generated types.
- [x] **Vertical slice verified live in-browser** (SMITH → Tarrant 47 / Dallas 54 streamed in order). **Phase 1 complete.**
- [ ] Sync `ARCHITECTURE.md` `SearchQuery`; tune Dallas paging latency. Then Phase 2 sources.

### 2026-06-10
- [x] Reviewed the existing demo (Next.js + Python versions) and extracted the reusable **knowledge** (source tiers, per-site gotchas) rather than the code.
- [x] **Live recon** beyond the demo: proved Hunt (open Sheriff Classic-ASP roster) and Oklahoma/ODCR (open, 1000 results) are reachable — both were wrongly marked "blocked"; Fannin's CAPTCHA found to be client-side (defeatable in-rules).
- [x] **Locked foundation decisions:** on-prem server · Python/FastAPI backend · React/Vite frontend · SSE streaming · SQLite (cache + audit) · adapter+contract+orchestrator pattern.
- [x] Wrote the foundation docs: `README`, `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/TECH_STACK.md`, `docs/SOURCES.md`, `docs/ADDING_A_SOURCE.md` (the pipeline), folder-skeleton READMEs, `.gitignore`, adapted `commit-style` skill.
- [x] Added the **plan-tracking** system (`plan.md` / `execution-map.md` / `last-point.md` + skill).
- [ ] Confirm team size → write the team-division doc.
- [ ] Commit the foundation + plan docs (branch `docs/foundation`, PR).
- [ ] Begin Phase 1 scaffold (start with the contract).
