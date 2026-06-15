# Hunt County, TX — Stage 1 raw-pull spike notes

**Hunt County Sheriff jail booking roster** — `https://apps.huntcounty.net/jail/` —
Classic **ASP / IIS** (`Microsoft-IIS/10.0`, `X-Powered-By: ASP.NET`), server-rendered
HTML. **Current-custody jail roster** → has **mugshots + charges** (on a per-inmate
detail page), no court dispositions. Tier 2, transport `http`. Captured 2026-06-15 via
`curl`. Fixtures alongside (git-ignored per `.gitignore`).

This is the **open** Hunt door. The county's `*.tylertech.cloud` **court** portal is
Tier-5 WAF-blocked; the Sheriff's `apps.huntcounty.net/jail/` booking system is wide
open ASP (same pattern as Tarrant: use the Sheriff roster, not the court portal).

## The load-bearing fact: NO server-side name search

The search form (`<form name="searchable" action="results.asp">`) has **only**
`start-date`, `end-date`, and `limit` (max 500) — **there is no name field.** `results.asp`
returns the **entire current jail population**. So the adapter pulls the full roster and
**filters by surname client-side** — the architecture's "search broad, rank/filter
client-side" stance (we don't trust dirty per-site filters; here there isn't even one).

## Request flow

1. **POST** `/jail/results.asp` (`start-date=""`, `end-date=""`, `limit=500`) → the full
   current roster as one HTML table `#bookings`. (Empty dates = current inmates; ~300 rows
   today, well under the 500 cap, so one page — no pagination needed. If it ever hits 500
   we mark the result `partial`.)
2. **POST** `/jail/booking.asp` (`partyID`, `jailingID`, `releaseDate=""`) → ONE inmate's
   detail page (mugshot + charges + personal details). Pulled lazily via `fetch_detail`.

### Load-bearing gotchas

- **`results.asp` is POST-only.** A bare `GET /jail/results.asp` returns 15 bytes (empty).
- **`booking.asp` is POST-only and validates its fields** — a GET, or wrong field names,
  returns a 200 page containing **"Invalid Form Sent"** (no data). The correct fields come
  from the roster JS: each row `<th data-party data-jailid data-released>` is wired (on row
  click) to submit a form to `booking.asp` with **`partyID`** (=`data-party`), **`jailingID`**
  (=`data-jailid`), **`releaseDate`** (=`data-released`, empty for current inmates).
- We pack `detail_id = "<partyID>-<jailingID>"` onto each list record so the UI's "More
  details" / photo-fetch can reach `fetch_detail`, which splits it back and POSTs booking.asp.
- **No DOB anywhere** — not on the roster, not on the detail (detail shows Race/Sex/Height/
  Weight only). So `year_of_birth` stays None.

## What you get / don't get

- **Roster list** (`#bookings`): each row is `<th …>NAME</th>` then `<td>` Gender, Race,
  Booking Date, Released Date. Name is `"SURNAME, FIRST MIDDLE"`. Released Date empty =
  currently in custody.
- **Detail** (`booking.asp`): **Personal Details** (Last/First/Middle, Race, Sex, Height,
  Weight, S/O Number, Location), a base64 **Mugshot** (`<img src="data:image/jpg;base64,…">`),
  and a **charges table**: Charge, Arrest Date, Arrest Ag., Charge Ag., Bond Type, Bond Amount.
- **No court dispositions** (jail roster, not court records) → `Charge.disposition` stays None.

## Field map → contract (`InmateRecord`)

| Hunt | InmateRecord |
| --- | --- |
| roster `<th>` name | `name` |
| roster Gender | `sex` (M/F; else None) |
| roster Booking Date | `booking_date` |
| roster Race | `raw["race"]` |
| `data-party` + `data-jailid` | `raw["detail_id"] = "<party>-<jail>"` (drives `fetch_detail`/photo) |
| detail mugshot (base64) | `photo_base64` (via `fetch_detail`) |
| detail Charge | `Charge.offense` |
| detail Arrest Date / Agencies / Bond | `Charge.extra` |
| — | `year_of_birth = None` (no DOB anywhere); `Charge.disposition = None` (jail roster) |
| own-roster name match | `matched_on = [NAME]` |

## Decisions

- **Client-side surname filter** (`_surname_matches`): keep a row if the query is a prefix
  of the whole surname (text before the first comma) **or** of any of its space/hyphen tokens
  — so `GONZALEZ` finds `ACOSTA GONZALEZ` and `SMITH` finds `SMITH-JONES`. Broad on purpose
  (possible matches for human review); approximates the "last name starts with" recall the
  server-side sources give.
- **One `InmateRecord` per inmate** (current custody). `total` = number of surname matches;
  `partial` when capped at `max_results` or when the roster itself hit the 500 limit.
- **Fail loud:** if `results.asp` returns no `#bookings` table, return ERROR — never a silent
  empty result.
- **Mugshots are an image source** (`fetch_detail` → booking.asp); the frontend auto-loads
  the first N at search (capped, concurrency-limited) like Tarrant, for the identity scan.

## Captured fixtures (git-ignored)

- `00_search_form.html` — the landing/search form (proves: only date + limit, no name field).
- `roster_current.html` — `POST results.asp` full current roster (~300 rows).
- `booking_174728.html` — `POST booking.asp` detail for one inmate (mugshot + 3 charges +
  personal details).

**Verified:** `POST results.asp` (limit=500) → full roster; client-side filter by surname →
matches; `POST booking.asp` (partyID/jailingID/releaseDate) → mugshot + charges; wrong fields
→ "Invalid Form Sent".
