# Tarrant — Stage 1 raw-pull spike notes

Sheriff inmate roster: `https://inmatesearch.tarrantcounty.com/` (ASP.NET MVC 5 + jTable,
IIS 10). **Current-custody only.** No CAPTCHA / WAF on the roster (the Tarrant *court* portal
is the Tier-5 WAF-blocked one — not this). Tier 1, transport `http`.

Captured fixtures live next to this file (`*.json` / `*.html`, git-ignored — real PII incl. a
base64 mugshot). Captured 2026-06-12 via plain `curl`.

## Request flow (3 calls for a full record)

A session cookie is set by `GET /` but does **not** appear to be required for the AJAX calls.
All POSTs are `application/x-www-form-urlencoded`; jTable replies `{"Result":"OK","Records":[...],"TotalRecordCount":N}`.

1. **List** — `POST /Home/GetSearchResults`
   - Search params: `lastName`, `firstName`, `cid`, `raceId`, `sexId`, `recordsId`
   - jTable params: `jtStartIndex`, `jtPageSize`, `jtSorting` (`FirstMiddleName ASC`)
   - Returns per row: `LastName, FirstMiddleName, Race, Sex, CID (key), DOB, InCustody`.
   - **No charges / no photo / no booking date in the list** — those need calls 2–3.
2. **Detail page** — `GET /Home/Details?CID=<cid>` → HTML containing the **mugshot inline as
   `data:image/jpg;base64,…`** (maps straight to `photo_base64`).
3. **Charges** — `POST /Home/GetActiveBookings` (and `POST /Home/GetNonCountyActiveBookings`),
   body just `cid=<cid>`. Each charge row: `Charge, CaseNumber, WarrantNumber, BookingNumber,
   Agency, BookInDate, BondType, BondSet, BondAmount, Condition, Hold, NoBondAllowed`.

## Load-bearing gotchas (the hard-won bits)

- **`raceId=All` and `sexId=Both` are required, not optional.** Sending empty strings (`raceId=`,
  `sexId=`) returns `Result:OK` with **zero records** — a silent false-negative, not an error.
  This is the trap: the call *looks* like it succeeded.
- **`recordsId` is the page size**, valid values `5/10/20/50` only (not an arbitrary int). It is
  *not* a record-type filter.
- Either `lastName` **or** `cid` is required (the UI enforces this client-side).
- **N+1 shape:** charges + photo are per-CID. A common surname (SMITH → 48 rows) would be
  48 detail + 48×2 booking calls to fully hydrate everyone → a rate-of-requests concern. The
  adapter should hydrate **lazily** (list first; fetch detail/charges only for rows the staff
  opens, or cap it), not eagerly loop all rows. Flag for the orchestrator/UI design.

## Field map → contract (`InmateRecord`)

| Tarrant | InmateRecord |
| --- | --- |
| `LastName` + `FirstMiddleName` | `name` |
| `DOB` (full `M/D/YYYY`) | `year_of_birth` (derive year; keep full DOB in `raw`) |
| `Sex` | `sex` |
| `BookInDate` (charge row) | `booking_date` |
| base64 on detail page | `photo_base64` |
| each booking row | a `Charge` (`offense`=Charge, `case_no`=CaseNumber, `warrant_no`=WarrantNumber, rest in `extra`) |
| n/a (always real-name search) | `matched_on` = `[NAME]` — Tarrant searches the roster name directly; no alias/attorney noise |

**Verified:** `lastName=SMITH` → 48 records; nonsense surname → `TotalRecordCount:0`; charges
returned for a real CID.
