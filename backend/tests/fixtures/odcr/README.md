# ODCR (Oklahoma) — Stage 1 raw-pull spike notes

**On Demand Court Records** — `https://odcr.com/` — a **statewide** Oklahoma court-case
index covering 70+ District Courts + several Tribal Courts in **one adapter**. nginx,
server-rendered HTML, `PHPSESSID`-style session cookie. **Court records, not a jail
roster** → has dispositions baked into the offense text, has **no mugshots, no DOB,
no sex/race** (a pure case index — name-only identity). Tier 2, transport `http`.
Captured 2026-06-15 via `curl`. Fixtures alongside (git-ignored per `.gitignore`).

This is the **open** Oklahoma door. OSCN (`oscn.net`, the state docket site) is
Tier-5 Cloudflare-Turnstile blocked; ODCR is the parallel public system and it is
wide open over plain HTTP. (ODCR's own results page even carries a client-side JS
cross-link to OSCN — `<section id="oscn-results" data-address="…oscn.net…">` — which
we ignore; it would hit the blocked door.)

## Request flow

Stateful within a session cookie. **POST-redirect-GET**, three steps:

1. **GET** `/` → sets the session cookie; serves the search form. Loads
   `recaptcha/api.js` (reCAPTCHA **v3**, invisible/score-based) — but the search
   below works over plain `curl` with **no token**, so v3 is non-blocking here. We do
   not solve, submit, or fake any token (in-scope: no security-control circumvention).
2. **POST** `/search` (form-urlencoded, same cookie) → **302 redirect to `/results`**.
   The query is stored server-side in the session; the POST body itself returns 0 bytes.
3. **GET** `/results` → the first page of results. Pagination is
   **`GET /results?page=N`** (carrying the cookie), ~15 rows/page.

Search form fields (POST `/search`):
| field | meaning | what we send |
| --- | --- | --- |
| `party` | **the name — `"LAST, FIRST"`** | `query.last` + `, ` + `query.first` (last-only if no first) |
| `party-type` | `P+D` (Plaintiffs & Defendants) / `All` | **`P+D`** — parties only, never attorneys |
| `court` | county code (`001-` Adair … `072-` Tulsa) or `""`=All | **`""`** (statewide; we rank client-side) |
| `court-group` | `""` / `Oklahoma District Courts` / `Tribal Courts` | `""` |
| `case-type`, `case-number-*`, `filed-start/end`, `activity` | optional filters | blank |

## Load-bearing gotchas

- **POST `/search` returns 302 → you MUST then GET `/results`.** The POST body is
  empty; the data lives behind the redirect, keyed to the session cookie. GET `/` first
  to obtain the cookie.
- **`party` is `"LAST, FIRST"`** (comma-separated), matching the form's "Last, First"
  label. Last-only (`"SMITH"`) is valid and broadest.
- **`party-type=P+D`** is the analog of Dallas's `nameType=DF`: it returns the actual
  **parties** (Defendants/Plaintiffs/etc.), not attorneys → this is the `matched_on`
  driver. Attorneys only appear under `party-type=All`, which we don't use.
- **Hard cap: "Limited to 1,000 results."** A common name statewide pages out to
  `/results?page=67` (~15/page). Like Dallas, we page with a dedup set and a time
  budget, and mark the result `partial` when we stop early.
- **`oscn-results` section is a client-side JS cross-link to the BLOCKED OSCN site** —
  ignore it. We parse only `<table id="results-list">`.
- **`additional-records-table` is an empty JS template** (`id="okcr-record-template"`,
  county land/instrument records loaded async) — **not** court cases. Ignore it too.

## What you get / don't get

- **List columns** (`#results-list`): `court` (county name), `case-number` (display
  `CM-2005-00249` + a stable detail link), `filed` (MM/DD/YYYY), `party` (name + a
  `<span class="type">` role: Defendant / Plaintiff / Person 1 / …), `case` (the
  caption, e.g. `STATE OF OKLAHOMA VS. SMITH, JOHN`), `offense` ("Offense or Cause").
- **Offense or Cause** blends offense + disposition with a **` - ST `** delimiter, e.g.
  `BEING DRUNK IN A PUBLIC PLACE - ST GUILTY PLEA`, `PROTECTIVE ORDER (DISMISSED) - ST
  DISMISSED`. Some rows have no ` - ST ` (e.g. `MARRIAGE LICENSE`) or are blank.
- **Stable detail link:** `/detail?court=<code>&casekey=<key>` — the `casekey` contains
  literal spaces (`003-CM  0500249`), URL-encoded as `+`. This is a stable ID → drives
  `source_url` and could drive `fetch_detail`.
- **No mugshots, no DOB, no sex, no race — anywhere** (verified on list AND detail). The
  detail page adds the docket (Case entries), full Parties Involved (incl. DA/Officer),
  Calendar events, and Receipts — but **no biographical identity data**. So ODCR matches
  are **name-only**; identity is confirmed by a human from case context.

## Field map → contract (`InmateRecord`)

| ODCR | InmateRecord |
| --- | --- |
| `party` name | `name` |
| `party` `<span class="type">` (Defendant/…) | `matched_on[0].detail` (type `NAME`) |
| `court` (county) | `Charge.extra["court"]` + `raw["court_name"]` |
| `case-number` display | `Charge.case_no` |
| `offense or cause` (before ` - ST `) | `Charge.offense` |
| `offense or cause` (after ` - ST `) | `Charge.disposition` (full text kept in `Charge.extra`) |
| `filed` | `Charge.extra["filed"]` (+ `raw`) |
| `case` caption | `raw["case_style"]` |
| `/detail?court=&casekey=` | `source_url` (+ `raw["casekey"]`, `raw["court_code"]`) |
| — | `year_of_birth`, `sex`, `photo_base64` = **None** (court index: none exist) |

## Decisions

- **One `InmateRecord` per result row** (per case), like Dallas — no person-level
  grouping in the adapter (ODCR has no DOB/identity key at all, so grouping would be
  pure guessing). Person-level dedup is deferred to the client-side ranking layer +
  human review.
- **Keep the full "Offense or Cause" verbatim.** We split on ` - ST ` into
  `offense` / `disposition` for parity with Dallas, but preserve the original string in
  `Charge.extra["offense_or_cause"]` so nothing is lost if the split is imperfect.
- **`matched_on = [NAME]`** with the party role in `.detail`. We search `party-type=P+D`
  (parties, not attorneys), so rows are real-name matches, never attorney noise.
- **`total`**: ODCR reports a count ("Limited to 1,000 results" / "N results"). We parse
  it into `AdapterResult.total`; `partial=True` whenever we stop before consuming it.

## Captured fixtures (git-ignored)

- `00_search_form.html` — the landing/search form (county codes, party-type, fields).
- `search_smithjohn_page1.html` — `party=SMITH, JOHN`, All Courts → page 1 (15 rows,
  "Limited to 1,000 results", pager to page 67).
- `search_smithjohn_page2.html` — `GET /results?page=2` (distinct rows; pagination proof).
- `search_no-results.html` — a nonsense party → title/body **"0 results"**, no
  `/detail` links (the no-results signal).
- `detail_atoka_cm0500249.html` — one case detail (Case Information / Parties Involved /
  Offense or Cause / docket) — confirms no DOB/sex anywhere.

**Verified:** `party=SMITH, JOHN` (P+D, All Courts) → 1,000-capped paginated results with
dispositions in the offense text; nonsense party → "0 results"; detail page pulled for
case `CM-2005-00249` (Atoka).
