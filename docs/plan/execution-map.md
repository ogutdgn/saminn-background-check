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

## CURRENT PHASE → Phase 2: Sources (in progress) — 4 of ~6 live
> **Phase 0 ✅** and **Phase 1 ✅** (the vertical slice runs end to end). Dated entries in [last-point.md](last-point.md).
>
> **Phase 1 (Scaffold) — core COMPLETE; 2 infra pieces deferred *by design* (not unfinished):**
> - [x] Backend setup · **contract** (`base.py`, structured `SearchQuery`) + registry · **orchestrator** (fan-out/stream/timeout/isolation) · **audit** (append-only SQLite) · **API** (`/api/search` SSE, `/api/health`, `/api/record/{source}/{id}`) · **frontend** (React/Tailwind/shadcn, OpenAPI-typed) · live vertical slice.
> - [ ] `browser.py` (Playwright manager) — **deferred to Collin** (build when the first browser source lands).
> - [ ] `cache.py` (SQLite TTL) — **deferred to Phase 4** (a volume optimization; unneeded at current volume).
>
> **Phase 2 (Sources) — in progress:**
> - [x] Tarrant (T1, http) · [x] Dallas (T2, http) — both live, with photos / case-sheet detail-on-demand.
> - [x] **ODCR (T2, OK statewide)** — live on `source/odcr`; one adapter for 70+ OK counties.
> - [x] **Hunt (T2)** — live on `source/hunt`; Sheriff roster + mugshot/charges detail (image source).
> - [ ] Denton (T3) · [ ] Collin (T4, browser — build `browser.py`) · [ ] Fannin (stretch).
>
> **Loose ends:** [x] `ARCHITECTURE.md` contract synced (2026-06-15). Open: tune Dallas paging latency
> (~18 s, worse with a first name — timed out at 30 s on SMITH/JOHN); tighten the Dallas name/DOB parser;
> replace the frontend `IMAGE_SOURCES` hardcode with a backend photo-capability flag; **merge `source/odcr`
> (and the `source/tarrant*` everything-branch) to `main`** — branch hygiene debt is growing. Team: **solo**.

## Daily work log

### 2026-06-15
- [x] **On-demand record detail:** `GET /api/record/{source}/{id}` + optional `Adapter.fetch_detail`. Tarrant: CID → mugshot + charges. **Dallas: Search-by-Case (stable case#) → full court case sheet** (richer than the list — full name, unmasked DOB).
- [x] **Frontend detail UX:** profile photos auto-loaded at search for image sources (capped/bounded); every record has **"More details" → popup (Dialog)**: Tarrant = big mugshot + charges, Dallas = document-styled case sheet (Courier, fixed-width columns, header bar).
- [x] **UI polish:** "No image" placeholders, search + popup **loading spinners**, wider/taller popup so the case sheet fits.
- [x] **Robustness:** `AdapterResult.partial` + Dallas time-budgeted pagination (no more timeout→0); detail fetch timeout + Retry; 60s dev-proxy timeout (Dallas detail is ~5–15s server-side). **38 tests pass.**
- [x] **Cleanup:** synced `ARCHITECTURE.md` contract spec (structured `SearchQuery`, `partial`, `fetch_detail`); clarified Phase-1 deferral (browser/cache).

**(2nd session) — ODCR source, full pipeline on `source/odcr`:**
- [x] **Stage 1 spike (live):** proved the ODCR pull — GET `/` (cookie) → POST `/search` (`party="LAST, FIRST"`, `party-type=P+D`) → 302 → `/results`, paged via `GET /results?page=N` (server caps at 1,000). Captured fixtures (page1/page2/no-results/detail/form) + spike notes `backend/tests/fixtures/odcr/README.md`.
- [x] **Stage 2 adapter** `adapters/odcr.py` (Tier 2, http): one record per case-row, ` - ST ` offense/disposition split (full text kept), `matched_on=NAME`+party role, stable `/detail` deep link; **no DOB/sex/photo** (court index). Registered disabled.
- [x] **Stage 3 tests** `test_odcr.py` (11): parsing, count, no-results, party-string, dedup pagination, max_results/time-budget `partial`, error isolation. **Full suite 49 pass** (was 38).
- [x] **Stage 4 enable + verify:** flipped enabled; verified live through the **orchestrator** (552 ms, OK, total=1000, partial) and the **SSE API** (`POST /api/search` → ODCR `result` event). Streams independently (Dallas timed out on the same query; ODCR unaffected). SOURCES.md → ODCR/Tarrant/Dallas `done`.
**(3rd session) — Hunt source, full pipeline on `source/hunt`:**
- [x] **Stage 1 spike (live):** proved the Hunt pull. Key discovery: **no server-side name search** — `results.asp` (POST, `limit≤500`) returns the *whole* current roster; we filter by surname client-side. Per-inmate detail via `booking.asp` (POST `partyID`/`jailingID`/`releaseDate`) → **mugshot + charges + personal details**; wrong fields → "Invalid Form Sent". Fixtures + notes `backend/tests/fixtures/hunt/README.md`.
- [x] **Stage 2 adapter** `adapters/hunt.py` (Tier 2, http): roster pull + `_surname_matches` (prefix/compound-token), `fetch_detail` (mugshot base64 + charges + personal), `detail_id="<party>-<jail>"`, fail-loud on missing table. **No DOB anywhere.** Registered.
- [x] **Stage 3 tests** `test_hunt.py` (16, incl. review-driven): field mapping, surname filter edges (incl. apostrophes), OK/no-match/capped-partial/error/timeout, fetch_detail (mugshot+charges), invalid-form/empty-name/bad-id → None, + real-capture smoke tests. **Full suite 66 pass** (was 49).
- [x] **Stage 4 enable + verify:** enabled; verified live — orchestrator (Hunt OK 3×GONZALEZ 233 ms) + live `fetch_detail` (42 KB mugshot + 3 charges). Frontend: added `"hunt"` to `IMAGE_SOURCES` (mugshots auto-load like Tarrant); `tsc` clean.
- [x] **Re-verified ODCR + Hunt together** (orchestrator): both OK ~0.2–2.4 s. One transient ODCR 30 s timeout on first run was **not reproducible** (4 subsequent runs fine) — handled by per-source timeout + isolation.
- [x] **Adversarial multi-agent review** (Workflow: 6 reviewers × 2 skeptics, 20 agents) of hunt.py + odcr.py → 7 findings, all on **Hunt** (ODCR clean). Fixed: partial-flag on a server-capped roster (even no-match), fail-loud on empty-name detail, specific charges-table detection, apostrophe/period surname recall (O'BRIEN~OBRIEN); added the missing TIMEOUT test (hunt + odcr); documented the deliberate keep-undeep-linkable-rows choice. **Full suite 66 pass.**
- [x] **Ran the full app** (uvicorn :8099 + Vite) and verified all 4 cards stream live (Tarrant 17 + mugshots, Dallas 54, ODCR 30/1000, Hunt 3 + mugshots). Hunt mugshots auto-load (confirmed `GET /api/record/hunt/...` 200s).
- [x] **fix(core): per-source timeout budget** — ODCR's cold `POST /search` (~16 s) intermittently tripped the flat 20 s per-source timeout → "Timed out" card. Added optional `Adapter.timeout_s`; orchestrator now uses a per-source budget (ODCR=45 s; jail rosters keep 20 s fail-fast). Verified live: ODCR → OK ~9 s. Dallas unchanged (self-limits paging to the budget).
- [x] **feat(odcr): return all + case sheet** (user ask) — ODCR now pages the FULL result set (up to its 1,000 server cap; `max_pages=70`), not `max_results`; and a per-record **case sheet** via `fetch_detail` (`/detail` → Case Information / Parties / docket), rendered like Dallas (generalized `CaseSheet`). **69 tests.** Verified live: GONZALEZ → 1,000 ODCR records (~14 s) + a record's "More details" shows the full sheet. **Tradeoff:** a common surname returns ~1,000 (slow/heavy, more timeout-prone on ODCR's cold POST) — narrowing with a first name is the intended path.
- [x] **Professional UI redesign** (user ask) — full pass over the SPA covering every flow: app header, contained search panel (Search/Clear/hint), live **results summary bar**, semantic per-source status (Match found / No matches / Timed out / error, color+icon), source-kind subtitles, amber partial note, whole-row record buttons with photo avatars + chevrons, and result lists **capped at 8 with "Show more"** (no more 1,000-row dumps). Enriched **`/api/health`** (`{id, display_name, transport, has_photos}`) → fixes both long-standing UI debts: the **"Odcr County" placeholder** and the **`IMAGE_SOURCES` hardcode** (now backend-driven `has_photos`). Verified live across idle / searching / ok / partial / timeout / detail dialog / mobile. **69 tests, tsc clean.**
- [x] Resolved: `IMAGE_SOURCES`→backend `has_photos` flag · "Odcr County" placeholder (now `/api/health` display names).
- [ ] Open: Dallas latency tuning · Dallas name/DOB parser · ODCR return-all is timeout-prone on common surnames (consider a sane cap) · merge `source/odcr`+`source/hunt`+everything-branch to `main` · **next source: Denton (T3) or Collin (T4 → `browser.py`)**.

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
