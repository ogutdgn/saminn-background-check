# Last Point — dated state checkpoints

> A running log of "where we are" at the end of each session/day. **Append a NEW dated entry at
> the TOP each time — never overwrite older entries.** The accumulated history shows our
> progression. Renewed via the `plan-tracking` skill. Big picture: [plan.md](plan.md) · session
> playbook + daily work log: [execution-map.md](execution-map.md).

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
