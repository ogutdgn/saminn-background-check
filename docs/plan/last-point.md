# Last Point — dated state checkpoints

> A running log of "where we are" at the end of each session/day. **Append a NEW dated entry at
> the TOP each time — never overwrite older entries.** The accumulated history shows our
> progression. Renewed via the `plan-tracking` skill. Big picture: [plan.md](plan.md) · session
> playbook + daily work log: [execution-map.md](execution-map.md).

---

## 2026-06-15 (4th session) — merge→main→GitHub; Denton (Tier 3) live: Phase 2 now 5 of ~6

- **Branch:** `source/denton` (Denton work; not yet merged). `main` now consolidated + pushed.
- **Phase:** **Phase 2 — 5 of ~6 live** (Tarrant, Dallas, ODCR, Hunt, **Denton**). First Tier-3 source.
- **State summary:** Consolidated all prior Phase-2 work into `main` and pushed to GitHub, then
  built **Denton** end-to-end — the first **Tier-3** (stateful Tyler Public Access) source.
- **Done this session:**
  - **UI:** ODCR "return all" + per-record case sheet; a full professional UI redesign; then —
    research-led (5-agent design-review workflow) — replaced the per-source grid with **one unified
    single-column results list** + a sticky control bar (source status/filter chips, sort, sex/
    birth-year/photo filters). The client-side filters are the fix for big result sets (e.g. ODCR's
    1,000). Enriched `/api/health` (`display_name`+`has_photos`) → killed the "Odcr County"
    placeholder + the `IMAGE_SOURCES` hardcode.
  - **Branch hygiene / GitHub:** merged `source/hunt` (39 commits: 4 sources + engine + API + UI)
    into `main`; reconciled with the user's pushed **PR #1** (Tarrant/Dallas) — clean, no force,
    PR preserved — and **pushed `main` to origin** (`origin/main` = the full app). Deleted the
    superseded `source/{hunt,odcr,tarrant-dallas}` branches. PII fixtures stayed git-ignored.
  - **Denton (Tier 3), full pipeline, live:** Cloudflare passes this IP. Cracked the Tyler Public
    Access flow (portal → POST `NodeID` "All JP & County Courts" → node-aware form → search POST →
    `CaseSearchResults.aspx`) and every magic field by walking the server errors. **The 0-record
    blocker was `BaseConnKy=DF`** (Defendant), not CaseTypeIDs. `adapters/denton.py` parses 400
    records (name + **birth year** + charge + disposition + court + `CaseDetail` deep link;
    `partial` at the 400 cap; `fetch_detail` = Register of Actions). **8 tests; full suite 77.**
    Verified live (orchestrator ~6.4 s; UI filtered-to-Denton renders correctly).
- **Next:** **Collin (T4)** — the browser source that finally builds the shared `browser.py`
  Playwright manager; then **Fannin** (stretch). Merge `source/denton` → `main` (+ push) when ready.
  Open: Dallas latency; ODCR common-surname timeout (optional cap); Denton **District Court** module
  (`PublicAccessDC/Search.aspx?ID=200`) for felonies.
- **Blockers/notes:** none. Denton is sensitive to IP reputation (recon note) but passes from here.

---

## 2026-06-15 (3rd session) — Hunt live + adversarial review: Phase 2 now 4 of ~6

- **Branch:** `source/hunt` (off `source/odcr`; not merged to `main`).
- **Phase:** **Phase 2 (Sources) — 4 of ~6 live** (Tarrant, Dallas, ODCR, **Hunt**).
- **State summary:** Built **Hunt County** end-to-end (add-a-source Stage 1→4), verified live, then
  ran an **adversarial multi-agent review** over both new adapters (Hunt + ODCR) and folded the
  confirmed fixes back in. Re-verified Hunt and ODCR both work properly (the user's explicit ask).
- **Done this session:**
  - **Stage 1 (spike, live):** discovered Hunt has **no server-side name search** — `results.asp`
    (POST, `limit≤500`) returns the *whole* current roster, so the adapter **filters by surname
    client-side**. Per-inmate detail via `booking.asp` (POST `partyID`/`jailingID`/`releaseDate`)
    → **mugshot + charges + personal details**; wrong fields → "Invalid Form Sent". Fixtures +
    notes (`backend/tests/fixtures/hunt/README.md`).
  - **Stage 2 (adapter):** `backend/adapters/hunt.py` (Tier 2, http). Roster pull + `_surname_matches`
    (prefix / compound-token / punctuation-normalized), `fetch_detail` (mugshot base64 + charges +
    personal), `detail_id = "<party>-<jail>"`, **fail-loud** on a missing `#bookings` table. No DOB
    anywhere. Registered + enabled.
  - **Stage 3 (tests):** `backend/tests/test_hunt.py` — 16 tests; **full suite 66 pass** (was 49).
  - **Stage 4 (enable + verify, live):** orchestrator (Hunt OK, 3× GONZALEZ, ~220 ms) + live
    `fetch_detail` (42 KB mugshot + 3 charges). Frontend: added `"hunt"` to `IMAGE_SOURCES` so
    mugshots auto-load like Tarrant; `tsc` clean.
  - **Both sources re-verified:** Hunt + ODCR run together fine (0.2–2.4 s). A one-off ODCR 30 s
    timeout was **not reproducible** (4 follow-up runs OK) — handled by per-source timeout + isolation.
  - **Adversarial review (Workflow, 20 agents):** 6 reviewers (2 adapters × correctness/contract/
    accuracy) → 2 skeptics per finding. **7 findings, all confirmed, all on Hunt; ODCR came back
    clean.** Fixed: (1) mark `partial` when the roster hit the server cap — even on a no-match;
    (2) `fetch_detail` returns None on an empty-name detail (fail loud, no empty identity);
    (3) charges-table detection requires its specific columns; (4) surname match normalizes
    apostrophes/periods (O'BRIEN ~ OBRIEN); (5) added the missing **TIMEOUT** test to hunt + odcr;
    (6) documented the deliberate choice to keep in-custody rows that can't be deep-linked (dropping
    a real inmate would be a worse, false-negative error).
- **Next:** **Denton** (T3, stateful Tyler) or **Collin** (T4 → build the shared `browser.py`).
  **Branch hygiene:** merge `source/odcr` + `source/hunt` + the everything-branch to `main`
  (debt is growing — 4 stacked source branches now). Loose ends unchanged (Dallas latency/parser;
  `IMAGE_SOURCES`→backend photo-capability flag).
- **Blockers/notes:** none for Hunt. Hunt's roster has no pagination yet (population ~314 << 500
  cap, so `partial` correctly signals the rare overflow); add roster paging if it ever nears 500.

---

## 2026-06-15 (2nd session) — ODCR live: Phase 2 now 3 of ~6 sources

- **Branch:** `source/odcr` (off the `source/tarrant*` everything-branch; not merged to `main`).
- **Phase:** **Phase 2 (Sources) — 3 of ~6 live** (Tarrant, Dallas, **ODCR**).
- **State summary:** Built the **Oklahoma ODCR** source end-to-end through the full add-a-source
  pipeline (Stage 1→4) and verified it live through the orchestrator and the SSE API. One adapter
  covers **70+ OK counties** statewide — high coverage-per-adapter.
- **Done this session:**
  - **Stage 1 (spike, live):** proved the pull — GET `/` (session cookie) → POST `/search`
    (`party="LAST, FIRST"`, `party-type=P+D`, `court=""`=statewide) **302→ `/results`**, paged with
    `GET /results?page=N` (~15/page; server **caps at 1,000**). Captured fixtures (page1/page2/
    no-results/detail/form, git-ignored) + spike notes (`backend/tests/fixtures/odcr/README.md`).
  - **Stage 2 (adapter):** `backend/adapters/odcr.py` (Tier 2, http). One `InmateRecord` per
    case-row (no person-grouping — ODCR has **no identity key**); `" - ST "` splits the
    "Offense or Cause" cell into offense/disposition (full text preserved in `extra`);
    `matched_on=NAME` + party role; stable `/detail?court=&casekey=` deep link. **No DOB/sex/
    mugshots anywhere** (court index → name-only matches). Registered disabled.
  - **Stage 3 (tests):** `backend/tests/test_odcr.py` — **11 tests** (parse, count=1000, "0 results",
    party-string build, dedup pagination across page1+page2, `partial` at max_results & time-budget,
    error isolation). **Full suite 49 pass** (was 38).
  - **Stage 4 (enable + verify):** flipped `enabled=True`; verified **live** via the orchestrator
    (OK, total=1000, partial, 552 ms, correctly parsed) and the **SSE API** (`POST /api/search` →
    ODCR `result` event, contract-shaped). Confirmed it **streams independently** — on SMITH/JOHN
    Dallas timed out at 30 s while ODCR returned fine (failure isolation working). SOURCES.md:
    ODCR + Tarrant + Dallas Build → `done`.
- **Architecture check:** no contract change needed — ODCR is a clean third adapter behind the
  same `Adapter`/`InmateRecord`/`AdapterResult` shapes; the engine/API/UI are untouched (the
  one-adapter-per-source pattern held for a court *index* with even less identity data than Dallas).
- **Next:** **Hunt** (T2, quickest — open Sheriff Classic-ASP roster) or **Denton** (T3, stateful
  Tyler). Then Collin (T4 → build `browser.py`). **Branch hygiene:** merge `source/odcr` (and the
  everything-branch) to `main` — debt is growing. Loose ends: Dallas latency (worse with a first
  name), Dallas name/DOB parser, `IMAGE_SOURCES`→backend photo-capability flag.
- **Blockers/notes:** none for ODCR. Dallas latency is the one pre-existing rough edge (its own
  loose end, not an ODCR issue).

---

## 2026-06-15 — Detail UX complete + architecture review + doc cleanup

- **Branch:** `source/tarrant` (still the everything-branch; not yet merged to `main`).
- **Phase:** **Phase 1 ✅ (core; browser/cache deferred by design). Phase 2 in progress — 2 of ~6 sources live.**
- **State summary:** Both live sources now have full detail UX (photos, popups, case sheet).
  Did an architecture review and a doc cleanup.
- **Done this session:**
  - **Dallas "More details"**: `fetch_detail` via **Search-by-Case** (stable case#, no session-relative
    link) → full court case sheet (richer than the list: full name, unmasked DOB).
  - **Detail popup (Dialog)** for every record: Tarrant = big mugshot + charges; Dallas =
    document-styled case sheet (Courier, fixed-width columns, header bar). Wider/taller popup.
  - **UI polish**: "No image" placeholders, search + popup loading spinners.
  - **Robustness**: `AdapterResult.partial` + Dallas time-budgeted paging (no timeout→0); detail
    fetch timeout + Retry; 60s dev-proxy timeout (Dallas detail is ~5–15s server-side). **38 tests pass.**
  - **Cleanup**: synced `ARCHITECTURE.md` contract spec to the evolved contract; clarified the
    Phase-1 deferral of `browser.py`/`cache.py` in the plan.
- **Architecture review (honest):** no *core* decision changed — adapter/contract/orchestrator,
  SSE, on-prem, SQLite, isolation, responsible-use all intact. The **contract evolved additively**
  (structured `SearchQuery`, `partial`, `fetch_detail`) — the planned "draft→validate→revise" path.
  Debt: small frontend `IMAGE_SOURCES` hardcode; branch hygiene (everything on `source/tarrant`,
  nothing merged to `main`); `browser.py`/`cache.py` still deferred.
- **Next:** pick the next **Phase-2 source** (ODCR = most coverage; Hunt = quickest), via the
  add-a-source pipeline. Optional first: merge the branch to `main`; tune Dallas latency.

---

## 2026-06-14 (detail + photos) — on-demand record detail + profile mugshots

- **Branch:** `source/tarrant`. **Phase 1 done + hardening/UX on the two live sources.**
- **Done:**
  - **Backend:** optional `Adapter.fetch_detail(id, ctx)` (contract, additive) + `GET
    /api/record/{source}/{id}`. Tarrant implements it (CID → mugshot + full charges via
    `hydrate`). Dallas not yet (its detail link is session-relative — would use Search-by-Case).
  - **Frontend:** each record has a **"More details"** expand; **image sources auto-load the
    booking photo** at search (first 12, concurrency 3) so staff get a visual identity check
    while scanning. Dallas shows list charges + the partial note (no photo).
  - **Dallas timeout fix** (earlier same day): `AdapterResult.partial` + time-budgeted paging —
    a common name returns partial results instead of timing out to zero.
  - **36 backend tests pass.** Verified live in-browser (GARCIA → 12 mugshots + 31 detail buttons;
    expand reveals charges).
- **Next:** Dallas "More details" (via Search-by-Case on the stable case number); tune Dallas
  paging latency; then **Phase 2 sources** (Hunt / ODCR / Denton → Collin → Fannin).

---

## 2026-06-14 (vertical slice) — Phase 1 COMPLETE, runs end to end

- **Branch:** `source/tarrant` (all Phase-1 scaffold work; not yet merged to `main`).
- **Phase:** **Phase 1 (Scaffold) — ✅ DONE. Phase 2 (Sources) next.**
- **State summary:** The vertical slice is real: type a name in the browser → both sources'
  cards stream in live. Backend spine + UI both built, tested, and verified end to end.
- **Done (this stretch):**
  - **API** (`backend/web/app.py`): FastAPI `POST /api/search` (SSE, one event per source via
    the orchestrator) + `GET /api/health`; audit wired; **Tarrant + Dallas enabled (Stage 4)**.
  - **Frontend** (`frontend/`): Vite + React + TS + Tailwind + **shadcn/ui**; an SSE-over-fetch
    client (`src/api/search.ts`), `SourceCard`, search box; **types generated from the backend
    OpenAPI** so they can't drift. `vite.config` proxies `/api` → `:8099`.
  - **Verified live in a real browser:** searching SMITH streamed **Tarrant (47 recs, 403 ms)**
    first, then **Dallas (54 recs across 3 paginated pages)** — completion-order streaming,
    contract rendering, charges/dispositions, and per-case records all confirmed on screen.
  - Fixed an SSE CRLF-parsing bug (sse-starlette uses `\r\n`). **31 backend tests pass.**
- **Next (Phase 2):** sources one at a time via the pipeline — Hunt, ODCR, Denton (HTTP) →
  Collin (build the shared `browser.py` Playwright manager) → Fannin (stretch).
- **Loose ends:** sync `ARCHITECTURE.md` to the structured `SearchQuery`; tune Dallas paging
  latency (~19 s on huge surnames — lower `page_delay_s`/`max_results` or hydrate lazily).
- **Run it:** backend `uvicorn web.app:app --app-dir backend --port 8099`; frontend `cd frontend
  && npm run dev` (proxies to the backend).

---

## 2026-06-14 (cont.) — Engine built + Dallas pagination solved

- **Branch:** `source/tarrant` (all Phase-1 scaffold work; not yet merged to `main`).
- **Phase:** **Phase 1 (Scaffold) — in progress.** Contract + 2 adapters + **engine** done; API/frontend next.
- **Done (this stretch):**
  - **Orchestrator** (`core/orchestrator.py`): `run_search()` async generator — concurrent
    fan-out to enabled adapters, hard per-source timeout, failure isolation, yields each
    `AdapterResult` in completion order (drives SSE). **Audit log** (`core/audit.py`):
    append-only SQLite. Stub-adapter tests.
  - **Dallas pagination solved** (was the Stage-4 blocker): `search()` follows `POST /paging`
    (`which=down`) + dedup set; stops on no-new-rows / `max_results` / `max_pages`. Verified
    against a live 3-page SMITH capture (54 distinct rows) and the prior demo's `dallas.ts`.
  - **28 tests pass.** Commits: `feat(core)…`, `feat(dallas): follow result pagination…`.
- **Next:** FastAPI `POST /api/search` SSE → React/Vite frontend + one card → **vertical slice**
  (enable Tarrant + Dallas, type a name, watch cards stream). Then sync `ARCHITECTURE.md`.
- **Notes:** Looked at the prior demo (`CODING/script-codes/samaritan-inn-scripts`) to confirm
  the Dallas paging technique. Both adapters still **disabled** until the slice enables them.

---

## 2026-06-14 — Phase 1: contract locked, Tarrant + Dallas adapters built & verified

- **Branch:** `source/tarrant` (foundation + adapters committed; not yet merged to `main`).
- **Phase:** **Phase 1 (Scaffold) — in progress.** Contract done; first two adapters done
  (Stage 2–3). Orchestrator / API / frontend still to come.
- **State summary:** Pivoted to "pull raw first, then lock the contract from real data."
  Pulled Tarrant (JSON) + Dallas (HTML) raw, built both adapters TDD against captured
  fixtures, and adversarially verified them. The one contract held across both opposite
  structures (jail JSON vs court HTML).
- **Done this session:**
  - **Stage-1 raw pulls** (live `curl`): Tarrant Sheriff jTable (list → detail base64 mugshot
    → bookings charges; gotcha: `raceId=All`/`sexId=Both` required) and Dallas Criminal
    Background Search (disclaimer-`captcha` gate → `searchByName`; court records → has
    dispositions, NO mugshots). Fixtures captured (git-ignored PII) + spike notes committed.
  - **Contract locked (v1):** `backend/adapters/base.py` — InmateRecord/Charge/AdapterResult/
    Adapter ABC/AdapterContext + a **structured `SearchQuery`** (last required + optional
    first/middle/sex/year_of_birth) replacing `name:str`. Registry + sanity tests.
  - **Adapters (Stage 2–3):** `tarrant.py` (lazy charge/photo hydration) + `dallas.py`
    (session flow, one record per case-row). Fixture-pinned via httpx MockTransport. Both
    registered **disabled**.
  - **Adversarial review** (3-agent workflow) caught a real grouping bug Dallas's own test
    missed (masked-DOB merge/split). Fixed → one record per case-row; `total=None`; Tarrant
    sex→None on unrecognized. Regression tests added. **19 tests pass.**
  - **Decisions:** solo (no team-division doc); **accuracy is the #1 requirement** (fail-loud,
    fixture-pinned, never fabricate); AI free-text search **deferred** (local-only,
    human-confirmed); **search broad + rank client-side** over trusting dirty per-site filters.
- **Next:**
  - **Orchestrator** (fan-out + per-source timeout + failure isolation + yield-as-it-lands) + audit log.
  - FastAPI `/api/search` SSE → React/Vite frontend + one card → the vertical slice.
  - **Sync `ARCHITECTURE.md`** contract spec to the new structured `SearchQuery`.
  - **Dallas Stage-4 blocker:** pagination (needs a real multi-page fixture before enabling).
- **Blockers/notes:** Dallas pagination unresolved (adapter stays disabled). Python 3.14 +
  no `uv` → used `venv`+`pip`. Commit `Co-Authored-By` trailer intentionally omitted (project
  commit-style overrides the global default).

---

## 2026-06-10 — Foundation: decisions locked, sources reconned, docs + pipeline written

- **Branch:** `main` (foundation docs staged on a `docs/foundation` branch for PR — not yet committed at time of writing).
- **Phase:** **Phase 0 (Foundation) — essentially DONE → Phase 1 (Scaffold) next.**
- **State summary:** went from a throwaway demo to a locked foundation. We kept only the demo's
  *knowledge* (source tiers + per-site gotchas), not its code — the project is a clean rewrite.
- **Done this session:**
  - **Live source recon** (beyond the demo's 4): confirmed **Hunt** reachable via the open Sheriff
    Classic-ASP roster (`apps.huntcounty.net/jail/`, `results.asp` returns the live roster, no
    CAPTCHA) and **Oklahoma via ODCR** (`odcr.com`, plain HTTP POST returned 1000 results; its
    reCAPTCHA is invisible v3, non-blocking). Both were previously marked "blocked" — wrong. Found
    **Fannin**'s CAPTCHA is **client-side JS** (defeatable within the rules), data via an
    `/api/data` backend; approach (browser vs reconstruct call) deferred. Tyler `*.tylertech.cloud`
    court portals + OSCN remain Tier-5 out-of-scope (server-side WAF/Turnstile).
  - **Locked decisions:** on-prem always-on server · Python 3.12+/FastAPI (async, SSE) · React
    (Vite+TS) frontend over SSE · SQLite (cache + audit) · one-adapter-per-source behind a Pydantic
    contract + registry + central orchestrator.
  - **Wrote foundation docs:** `README.md` (rewritten), `CLAUDE.md`, `docs/ARCHITECTURE.md` (layers,
    data flow, full contract spec, responsible-use rules), `docs/TECH_STACK.md` (locked + deferred +
    rejected), `docs/SOURCES.md` (tier system + status table from recon), `docs/ADDING_A_SOURCE.md`
    (the **5-stage pipeline** with review gates + Adapter checklist + recon template).
  - **Folder skeleton** (docs-only, no implementation files): `backend/{adapters,core,web,tests}/`
    + `frontend/`, each with a purpose README; `.gitignore` (with PII guards); adapted
    `commit-style` skill; this **plan-tracking** system.
- **Next:**
  - Confirm **team size** (you + 5, or 5 total) → write the **team-division** doc (owners for the
    Phase-1 subsystems and Phase-2 counties).
  - **Commit** the foundation + plan docs (branch `docs/foundation` → PR to `main`).
  - Start **Phase 1 scaffold**, beginning with the **contract** (`adapters/base.py`) since
    everything depends on it.
- **Blockers/notes:**
  - Nothing technical blocking. The only open *process* item is team division (needs team size).
  - Reminder: files like `adapters/collin.py` intentionally **do not exist yet** — created phase by
    phase via the pipeline.
  - Fixtures with real PII are git-ignored by default; confirm the policy with the lead before
    committing any fixture.
