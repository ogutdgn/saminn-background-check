# Adding a Source — the pipeline

This is **the** process doc. When the lead assigns you a county ("you take Collin,
you take Dallas"), this is what you do. It is a 5-stage pipeline with a **review
gate** between stages. The gates exist so we catch a wrong turn early — before
someone has written 300 lines of adapter against the wrong endpoint.

**Do not skip stages and do not skip ahead to writing the adapter.** The expensive
mistakes in this kind of project happen in Stages 0–1 (picking the wrong door,
not understanding how the data really loads). The adapter itself is the easy part.

```
Stage 0          Stage 1            Stage 2          Stage 3        Stage 4
RECON       →    DATA-PULL SPIKE →  ADAPTER     →    TESTS &    →   INTEGRATE
(find the        (prove you can     (implement       FIXTURES       & ENABLE
 open door)       pull it raw)       the contract)   (lock it in)   (go live)
   │ gate ▲         │ gate ▲           │ gate ▲        │ gate ▲        │ gate ▲
   └─ lead OKs ─────┴─ lead OKs ───────┴─ code review ─┴─ tests pass ──┴─ lead verifies
      the door &       the raw pull       against the    in CI          end-to-end,
      the tier         + fixture          checklist                     then merge
```

Each stage is a small, reviewable unit of work. Commit per stage (see commit
style). One branch per source: `source/<county>`.

---

## Stage 0 — Recon (find the open door)

**Goal:** identify the *best public door* into this county's data and classify its
tier. **No adapter code in this stage.**

**Do:**
1. Find **every** door, not the first one: county court portal, Sheriff/jail roster,
   statewide system (re:SearchTX, ODCR), and any vendor site. Remember the lesson:
   a blocked court portal says nothing about an open Sheriff roster.
2. For each candidate door, probe (browser devtools, `curl -i`, view-source):
   - What tech is it? (IIS/ASP, ASP.NET WebForms, a SPA, a JSON API…)
   - **Is there a real API**, or is it HTML you'd parse?
   - **Bot protection?** Distinguish **server-side** (CAPTCHA/WAF — likely Tier 5,
     out of scope) from **client-side** (JS gate — defeatable within the rules).
   - Does it need a browser, or will plain HTTP work?
3. Pick the door and assign a **tier** (see `SOURCES.md`).
4. **Check the responsible-use rules.** If the only door is a server-side wall, the
   answer is "out of scope," not "let's beat it."

**Deliverable:** a filled-in row + notes in [`SOURCES.md`](SOURCES.md), using the
recon template at the bottom of this doc.

**🚦 Gate:** the lead confirms the chosen door and tier before any pulling code.
This five-minute check prevents days of work on the wrong system.

---

## Stage 1 — Data-pull spike (prove it raw)

**Goal:** prove you can pull real data **outside** the app, with the minimum
requests, and capture it. This is throwaway exploration, *not* the adapter.

**Do:**
1. Reproduce the search by hand with `curl` / a scratch script / Playwright codegen:
   - The exact request(s): URLs, method, form fields, headers, cookies/session.
   - The **load-bearing details** — the one magic field, the token that must be
     replayed, the keypress the JS framework actually listens for. Write these down;
     they are the hard-won knowledge.
2. Run a query that returns **several** results and one that returns **none**.
3. **Capture a real raw response** and save it as a fixture under
   `backend/tests/fixtures/<county>/` (raw HTML/JSON). This makes the rest of the
   work offline-testable and is the proof the pull works.

**Deliverable:** the captured fixture(s) + a short note (in the PR or the source's
notes) describing the exact request flow and any gotchas.

**🚦 Gate:** the lead sees the raw pull working and the fixture committed. We now
*know* the data is reachable before investing in a clean adapter.

---

## Stage 2 — Adapter (implement the contract)

**Goal:** a clean `backend/adapters/<county>.py` that turns the raw pull into
`InmateRecord`s, behind the shared `Adapter` contract.

**Do:**
1. Create `backend/adapters/<county>.py` implementing `Adapter` (see
   `backend/adapters/README.md` for the template and `ARCHITECTURE.md` for the
   contract).
2. HTTP sources use `httpx`; browser sources use the **shared browser manager** —
   never spin up your own browser, never use raw `requests`.
3. Map raw fields → `InmateRecord`. Fill `charges`. **Populate `matched_on`** so the
   UI can tell real-name matches from attorney/alias noise — this is part of the
   adapter's job.
4. Handle the four `AdapterStatus` outcomes: `ok`, `no_results`, `error`, `timeout`.
   Never return unfiltered/garbage data silently — fail loudly with a clear `error`.
5. Register it in `backend/adapters/registry.py` — **disabled by default** at first.

**Deliverable:** the adapter + a one-line registry entry.

**🚦 Gate:** code review against the **Adapter checklist** below.

---

## Stage 3 — Tests & fixtures (lock it in)

**Goal:** the adapter is verified against captured fixtures so we can run the suite
without touching live sites.

**Do:**
1. Write a fixture-based test in `backend/tests/` that feeds the Stage-1 fixtures
   through the adapter and asserts the parsed `InmateRecord`s.
2. Cover at least: a **multi-result** query (incl. pagination if the source pages),
   a **no-results** query, and correct `matched_on` tagging.
3. Make sure the suite is green.

**Deliverable:** passing tests committed alongside the adapter.

**🚦 Gate:** tests pass in CI.

---

## Stage 4 — Integrate & enable (go live)

**Goal:** the source is wired into the running app and visible to staff.

**Do:**
1. Flip the source to **enabled** in the registry.
2. Run the whole app; confirm the orchestrator fans out to it and the UI renders its
   card (ok / no-results / error states all look right).
3. Confirm it streams independently — a slow or failing source doesn't block others.
4. Update its **status to `done`** in `SOURCES.md`.

**Deliverable:** the source live behind the search box.

**🚦 Gate:** the lead verifies end-to-end, then the branch merges to `main` (PR).

---

## The Adapter checklist (used at the Stage 2 gate)

- [ ] Implements the `Adapter` contract; returns `AdapterResult` with a valid status.
- [ ] HTTP via `httpx` **or** browser via the **shared manager** — not raw
      `requests`, not a private browser instance.
- [ ] Maps to `InmateRecord` correctly; `charges` populated where available.
- [ ] **`matched_on` populated** so real-name vs attorney/alias is distinguishable.
- [ ] Handles pagination (if the source pages) and asserts it actually advanced —
      never silently returns page 1 or an unfiltered list.
- [ ] All four outcomes handled: `ok`, `no_results`, `error`, `timeout`. Errors are
      explicit, never silent bad data.
- [ ] Respects cancellation / the per-source timeout.
- [ ] Human-paced; no aggressive looping that would trip bot-protection.
- [ ] No cross-adapter imports. No scraping logic leaking into `web/` or `frontend/`.
- [ ] Registered in `registry.py`.
- [ ] Fixture(s) captured; test added (Stage 3).
- [ ] Stays inside the responsible-use rules (public data, no security-control
      circumvention).

---

## Stage 0 recon template (paste into SOURCES.md notes)

```
### <County> recon — <date> — <your name>

Doors checked:
- <url 1> — <tech> — <API? bot protection? server- or client-side?> — verdict
- <url 2> — ...

Chosen door: <url>
Tier: <1-5>
Transport: http | browser
Bot protection: none | client-side (defeatable) | server-side (OUT OF SCOPE)
Photos: yes/no
Load-bearing details / gotchas: <the magic field, the token, the keypress, etc.>
Responsible-use check: <within rules? why?>
```
