# Last Point — dated state checkpoints

> A running log of "where we are" at the end of each session/day. **Append a NEW dated entry at
> the TOP each time — never overwrite older entries.** The accumulated history shows our
> progression. Renewed via the `plan-tracking` skill. Big picture: [plan.md](plan.md) · session
> playbook + daily work log: [execution-map.md](execution-map.md).

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
