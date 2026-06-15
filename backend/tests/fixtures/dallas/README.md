# Dallas — Stage 1 raw-pull spike notes

Dallas County **Criminal Background Search** (Felony & Misdemeanor *court* case info):
`https://www.dallascounty.org/criminalBackgroundSearch/` — Apache/Java (JSESSIONID), server-rendered
HTML. **Court records, not a jail roster** → has **dispositions**, has **no mugshots**. Tier 2,
transport `http`. Captured 2026-06-12 via `curl`. Fixtures alongside (git-ignored).

## Request flow

Stateful within a `JSESSIONID` session. Three steps:

1. **GET** `/criminalBackgroundSearch/` → sets `JSESSIONID`; serves a **disclaimer / terms gate**.
   - ⚠️ The form is `<form action="captcha" name="captcha">` — **named "captcha" but it is NOT a
     CAPTCHA.** No reCAPTCHA/hCaptcha/Turnstile, no sitekey, no challenge image — just a
     "DISCLAIMER, TERMS & CONDITIONS OF USE" block with a single **Continue** button. Accepting a
     public terms gate is in-scope (not security-control circumvention).
2. **POST** `/criminalBackgroundSearch/captcha` (body `submit=Continue`, same session cookie) →
   unlocks and returns the real search form (`searchByName` + `searchByCase`).
3. **POST** `/criminalBackgroundSearch/searchByName` → results table. Fields:
   `lastName` (required), `firstName`, `middleName`, `nameType`, `race`, `sex`,
   `dobMonth/dobDay/dobYear`, `numberType`, `pending`, `searchbyname=Search By Name`.

## Load-bearing gotchas

- **Must POST the disclaimer first**, in-session, before `searchByName` will work. (Recon's
  "no bot protection" was right that there's no CAPTCHA — but missed this session gate.)
- **Blank IS the default filter** here (`race=' '`, `sex=' '`, empty dob = "any"). Opposite of
  Tarrant — do NOT send "All". Sending blanks is correct.
- **`nameType`** = `DF` Defendant / `BN` Bondsman / `DD` Defense Attorney. **Search `DF`** for the
  person → this is the `matched_on` driver (searching `DD` would return attorney matches).
- **Result is one row per charge/case** (name repeats). We deliberately do **NOT** group
  rows into persons in the adapter — see "Known gaps" below.
- **Pagination:** the results page has a `Page Down` control (`<form name="paging">`). Large
  surnames span multiple pages.
- **Detail page is session-stateful:** `GET defendant_detail?ln=<rownum>` where `ln` is the row's
  index *in the current search session* — not a stable ID. Must fetch in the same session, in order.
- **Detail is a fixed-width mainframe text screen** (CICS-style, `&nbsp;`-padded), not clean table
  cells — parse by field labels/columns, not `<td>`. `disp_codes.jsp` is the legend for DISP codes.
- County **masks PII** on detail (address/SSN `****`, DOB often `00000000`). Respect that.

## What you get / don't get

- **List columns:** `LN` (name), `RS` (race+sex combined, e.g. `WM`), `DOB` (`MMDDYY`, often `000000`),
  `CASE/BOND`, `CT` (court), `CHARGE` (abbreviated codes, e.g. `FMFR`, `ROB FA`), **`DISP`** (disposition
  code, e.g. `DISM`=dismissed).
- **Detail adds:** DA + judicial case IDs, file date, full charge / reduced-enhanced charge,
  disposition, hearing schedule (SETS AND PASSES), and a `NAMES`/alias section.
- **No photos, anywhere** (verified on list and detail — only the page banner img). `photo_base64`
  stays null for Dallas, by design.

## Field map → contract (`InmateRecord`)

| Dallas | InmateRecord |
| --- | --- |
| `LN` | `name` |
| `RS` (split, e.g. `WM`→ sex `M`) | `sex` (+ race → `raw`) |
| `DOB` (`MMDDYY`, masked `000000`) | `year_of_birth` if present else null (full → `raw`) |
| `CHARGE` code | `Charge.offense` |
| `CASE/BOND` | `Charge.case_no` |
| **`DISP`** | **`Charge.disposition`** ← the field Tarrant lacked |
| `CT`, reduced/enhanced, file date | `Charge.extra` |
| `nameType=DF` search | `matched_on = [NAME]` (DD would be `ATTORNEY`); alias via `NAMES` section |
| — | `photo_base64 = None` (no mugshots in court records) |

## Known gaps & decisions (from adversarial review)

- **No person-grouping in the adapter — one `InmateRecord` per case-row.** Dallas's list has no
  reliable person key: the DOB is frequently masked (`000000`). Grouping on `(name, DOB)` would
  both *split* one person across masked/unmasked rows (e.g. `SMITH JAMES DOUGLAS` rows with
  `000000` vs `092256`) and *merge* two distinct same-name people who both have a masked DOB —
  either is "silently wrong". So we emit one record per case and defer person-level dedup to the
  client-side ranking layer (confidence + human review). Regression tests pin both cases.
- **`total` is `None`** — Dallas reports no result count, and we don't yet page.
- **🚧 Pagination is a Stage-4 (enable) blocker.** `search()` reads page 1 only; multi-page
  surnames silently lose later pages. Need a real multi-page capture, then follow the `paging`
  `Page Down` POST. The adapter stays **disabled** until this is handled.

**Verified:** `lastName=SMITH` (Defendant) → multi-row results w/ dispositions; nonsense surname →
"No records were found using the search criteria provided"; detail page pulled for row 01.
