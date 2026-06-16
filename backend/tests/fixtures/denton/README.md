# Denton County, TX — Stage 1 raw-pull spike notes (IN PROGRESS)

Denton County **Tyler "Public Access"** (legacy Odyssey portal), *self-hosted* at
`https://justice1.dentoncounty.gov/PublicAccess/`. ASP.NET WebForms, **Tier 3**
(stateful — must replay `__VIEWSTATE`/`__EVENTVALIDATION` and set JS-populated "magic
fields"). Transport `http`. Spiked 2026-06-15.

**Status: flow PROVEN, but the name search currently returns 0 records — one blocker
remains (`CaseTypeIDs`, below). Not yet adapter-ready.**

## Reachability (the recon risk — CLEARED)

Cloudflare sits in front (`server: cloudflare`, `__cf_bm` cookie), and the recon flagged
"datacenter IPs may be challenged." **From this environment it is NOT challenged** — the
initial GET returns the real 302 → `/PublicAccess/default.aspx` with a normal ASP session
cookie, no "Just a moment" wall. So Denton is reachable here (no browser needed for the
pull itself).

## The request flow (Tyler Public Access)

The portal `default.aspx` exposes search menus via `LaunchSearch('<page>?ID=<n>', …)`:
| Menu | Page | What |
| --- | --- | --- |
| **JP & County Court: Criminal Case Records** | `Search.aspx?ID=100` | **← the criminal name search we want** |
| JP & County Court: Civil/Family/Probate | `Search.aspx?ID=200` | |
| District Court Case Records | `../PublicAccessDC/Search.aspx?ID=200` | felonies — a separate module, also worth adding |
| Jail / Jail Bond Records | `JailingSearch.aspx?ID=400/500` | |

`LaunchSearch` for `ID=100` carries a **NodeID** (the court selection) — it builds a form
and POSTs `NodeID` + `NodeDesc` to `Search.aspx?ID=100`. The node selector `sbxControlID2`
offers per-court values and an **"All JP & County Courts"** value (a comma-list):
`1,1101,1110,1102,1003,1104,1105,1106,1107,1108,1270,1280,1310,1320,1330,1340,1350,1360`.

**Proven flow:**
1. **GET** `/PublicAccess/default.aspx` → session cookie (ASPSESSIONID).
2. **POST** `/PublicAccess/Search.aspx?ID=100` with `NodeID=<allcourts>` + `NodeDesc` →
   the **node-aware search form** (159 KB; has fresh `__VIEWSTATE`).
3. **POST** `/PublicAccess/Search.aspx?ID=100` with the search params (below) →
   `CaseSearchResults.aspx` renders **"Criminal Case Records Search Results"** with the
   real columns: Case Number · Citation Number · Defendant Info · Filed/Location/Judicial
   Officer · Type/Status · Charge(s).

## The "magic fields" (cracked, via `ValidateSearchParameters()`)

For a **Party → Name** search (`SearchBy=1`, `PartySearchMode=Name`):
| field | value | note |
| --- | --- | --- |
| `SearchBy` | `1` | Party (0=Case, 2=Attorney, 5=Citation, 6=DateFiled) |
| `SearchType` | `PARTY` | (NOT "CASE" — that bounces) |
| `SearchMode` | `NAME` | |
| `NameTypeKy` | `ALIAS` | what the JS sets for a party name search |
| `LastName` / `FirstName` / `MiddleName` | the name | last-only is allowed |
| `NodeID` | the all-courts comma-list | empty `NodeID` → **bounce to `default.aspx`** |
| `AllStatusTypes` `StatusType` `ShowInactive` `RequireFirstName` `ExactName` | `true/true/false/False/false` | **empty → `Boolean.Parse` FormatException** at render |
| `SortBy` | `casenumber` | a `<select>`; empty → "SortBy is invalid" |
| `SearchSubmit` | `Search` | |
| + all `__VIEWSTATE` / `__VIEWSTATEGENERATOR` / `__EVENTVALIDATION` | replay verbatim | |

Each was found by iterating the live server's error messages (bounce → Boolean error →
SortBy error → clean 0-record page).

## ⚠️ The remaining blocker — `CaseTypeIDs` (next step)

The clean results page reports **"Record Count: 0 — No cases matched"** for `SMITH`, which
is wrong. Cause: the hidden **`CaseTypeIDs`** (which case categories to search) is **empty**.
In the browser it's populated from the page's embedded case-type data (a JS structure;
`document.getElementById("CaseTypeIDs").value = caseTypeIDs`) — there is **no AJAX endpoint**
(only `Search/MyAccount/default/logout.aspx` exist), so the case types are embedded in the
~157 KB form, not fetched. **Next step:** extract the full case-type ID list from the form's
embedded data (or the node-aware form) and submit `CaseTypeIDs=<all ids>` (likely a comma
list), then re-run — that should turn 0 into real rows. After that: capture a multi-result
fixture + a no-results fixture, then build the adapter.

## Captured artifacts (git-ignored)

- `00_search_form_ID100.html` — the GET search form (fields, `__VIEWSTATE`, the JS).
- `results_smith_0records.html` — a clean (but empty) results page proving the mechanism.

## Field map → contract (planned, once results flow)

Court records → dispositions in the charge/status; **no mugshots**. Columns map: Defendant
Info → `name` (+ DOB/sex if present in the cell) · Case Number → `Charge.case_no` ·
Charge(s) → `Charge.offense` · Type/Status → `Charge.disposition`/`extra` · the
`CaseDetail.aspx` link → `source_url` + `fetch_detail` (Register of Actions). `matched_on =
NAME` (party search). One record per case-row, like Dallas/ODCR.
