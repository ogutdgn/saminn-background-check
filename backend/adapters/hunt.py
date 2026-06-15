"""Hunt County, TX — Sheriff jail booking roster (Tier 2, http).

Classic ASP / IIS jail roster at apps.huntcounty.net/jail/. **Current-custody only**;
has mugshots + charges on a per-inmate detail page. Spike notes + field map:
backend/tests/fixtures/hunt/README.md.

**Load-bearing fact: the roster has NO server-side name search.** `results.asp` returns
the WHOLE current jail population — the form only has `start-date` / `end-date` / `limit`.
So we pull the full roster and **filter by surname client-side** (the architecture's
"search broad, rank/filter client-side" stance — the same reason we don't trust dirty
per-site filters). Flow:

  POST results.asp (start-date="", end-date="", limit=500)  -> full current roster (HTML table)
  POST booking.asp (partyID, jailingID, releaseDate="")     -> ONE inmate's detail page
       (base64 mugshot + charges + personal details) — pulled lazily via `fetch_detail`.

The detail form fields are `partyID` (row `data-party`), `jailingID` (row `data-jailid`),
`releaseDate` (row `data-released`, empty for current inmates). We pack party+jail into the
record's `detail_id` so the UI's "More details" / photo fetch can reach `fetch_detail`.

Accuracy: the roster row gives name, sex, race, booking date — **no DOB anywhere** (not on
the list and not on the detail), so `year_of_birth` stays None. Every row is an own-roster
name match -> `matched_on = NAME`. Surname matching (see `_surname_matches`) is a prefix/
token match, broad enough for compound/hyphenated names; results are possible matches for
human review.
"""
from __future__ import annotations

import re

import httpx
from selectolax.parser import HTMLParser

from .base import (
    Adapter,
    AdapterContext,
    AdapterResult,
    AdapterStatus,
    Charge,
    InmateRecord,
    MatchInfo,
    MatchType,
    SearchQuery,
)

_BASE = "https://apps.huntcounty.net/jail"
_MUGSHOT_RE = re.compile(r"data:image/[a-zA-Z]+;base64,([A-Za-z0-9+/=]+)")


class HuntAdapter(Adapter):
    id = "hunt"
    display_name = "Hunt County"
    transport = "http"
    tier = 2

    RESULTS_URL = f"{_BASE}/results.asp"
    BOOKING_URL = f"{_BASE}/booking.asp"
    LIMIT = 500   # the form's max; the current population fits well under this in one page

    async def search(self, query: SearchQuery, ctx: AdapterContext) -> AdapterResult:
        start = ctx.now_ms()
        try:
            # Pull the WHOLE current roster (no name field exists on this site).
            resp = await ctx.http.post(
                self.RESULTS_URL,
                data={"start-date": "", "end-date": "", "limit": str(self.LIMIT)},
                timeout=ctx.timeout_s,
            )
            resp.raise_for_status()
            tree = HTMLParser(resp.text)
            table = tree.css_first("#bookings")
            if table is None:
                # No roster table and no recognizable shape -> fail loud (never silent bad data).
                raise ValueError("roster page had no #bookings table")

            roster = self._parse_roster(table)
            # If the roster itself hit the server limit it was TRUNCATED — so every outcome below
            # (even a no-match) is uncertain and must be marked `partial`; a match could lie past
            # the cap. (Today's population is well under 500; this guards a future overflow.)
            roster_capped = len(roster) >= self.LIMIT
            q = (query.last or "").strip().upper()
            matched = [r for r in roster if self._surname_matches(r.name, q)]
            if not matched:
                return self._envelope(AdapterStatus.NO_RESULTS, [], 0, start, partial=roster_capped)

            total = len(matched)
            partial = roster_capped
            if total > query.max_results:
                matched = matched[: query.max_results]
                partial = True  # more surname matches exist than we returned
            return self._envelope(AdapterStatus.OK, matched, total, start, partial=partial)
        except httpx.TimeoutException as e:
            return self._fail(AdapterStatus.TIMEOUT, start, str(e))
        except Exception as e:  # never raise out of search()
            return self._fail(AdapterStatus.ERROR, start, str(e))

    async def fetch_detail(self, record_id: str, ctx: AdapterContext) -> InmateRecord | None:
        """Detail-by-(party,jail): mugshot + charges + personal details for one inmate, via a
        POST to booking.asp. `record_id` is "<partyID>-<jailingID>" (from the list `detail_id`).
        The frontend merges this onto the list record it already has. Never raises -> None on
        failure."""
        try:
            party, _, jail = record_id.partition("-")
            if not party or not jail:
                return None
            resp = await ctx.http.post(
                self.BOOKING_URL,
                data={"partyID": party, "jailingID": jail, "releaseDate": ""},
                timeout=ctx.timeout_s,
            )
            resp.raise_for_status()
            html = resp.text
            if "Invalid Form" in html:
                return None  # booking.asp rejects the form -> nothing to show
            d = self._parse_booking(html)
            if not d["name"]:
                return None  # no parseable name -> fail loud (never return an empty identity)
            return InmateRecord(
                source=self.id,
                name=d["name"],
                sex=d["sex"],
                photo_base64=d["photo"],
                matched_on=[MatchInfo(type=MatchType.NAME)],
                charges=d["charges"],
                raw={
                    "detail_id": record_id,
                    "race": d["race"],
                    "height": d["height"],
                    "weight": d["weight"],
                    "personal": d["personal"],
                },
            )
        except Exception:
            return None

    # -- pure parsers (fixture-tested) ------------------------------------

    def _parse_roster(self, table) -> list[InmateRecord]:
        """Every current inmate (pre-filter). Columns after the name <th>:
        Gender, Race, Booking Date, Released Date."""
        out: list[InmateRecord] = []
        for row in table.css("tbody tr"):
            th = row.css_first("th")
            if th is None:
                continue
            name = " ".join(th.text().split())
            if not name:
                continue
            vals = [td.text(strip=True) for td in row.css("td")]
            gender = vals[0] if len(vals) > 0 else None
            race = vals[1] if len(vals) > 1 else None
            booking = vals[2] if len(vals) > 2 else None
            released = vals[3] if len(vals) > 3 else None
            party = th.attributes.get("data-party")
            jail = th.attributes.get("data-jailid")
            # detail_id is None if a row lacks the ids — we still KEEP the record: the person is
            # really in custody (name + booking are the primary intake answer), they just can't be
            # detail-fetched. Dropping them would be a false negative — worse than no mugshot. The
            # frontend treats a null detail_id as "no More-details/photo", and fetch_detail rejects
            # a malformed id, so a missing id degrades gracefully rather than erroring.
            detail_id = f"{party}-{jail}" if party and jail else None
            out.append(
                InmateRecord(
                    source=self.id,
                    name=name,
                    year_of_birth=None,             # no DOB on the roster (or the detail)
                    sex=self._norm_sex(gender),
                    booking_date=booking or None,
                    matched_on=[MatchInfo(type=MatchType.NAME)],
                    raw={
                        "race": race or None,
                        "released": released or (th.attributes.get("data-released") or None),
                        "party_id": party,
                        "jail_id": jail,
                        "detail_id": detail_id,      # "<party>-<jail>" -> fetch_detail / UI photo
                    },
                )
            )
        return out

    def _parse_booking(self, html: str) -> dict:
        """Parse the booking.asp detail page: Personal Details (label/value), the base64
        mugshot, and the charges table (Charge / Arrest Date / Arrest Ag. / Charge Ag. /
        Bond Type / Bond Amount)."""
        tree = HTMLParser(html)
        personal: dict[str, str] = {}
        for grp in tree.css(".form-group"):
            label = grp.css_first("label")
            inp = grp.css_first("input")
            if label is None or inp is None:
                continue
            personal[label.text(strip=True)] = (inp.attributes.get("value") or "").strip()

        last = personal.get("Last Name", "").strip()
        first = personal.get("First Name", "").strip()
        middle = personal.get("Middle Name", "").strip()
        name = None
        if last:
            fm = " ".join(p for p in (first, middle) if p)
            name = f"{last}, {fm}" if fm else last

        m = _MUGSHOT_RE.search(html)
        return {
            "name": name,
            "race": personal.get("Race") or None,
            "sex": self._norm_sex(personal.get("Sex")),
            "height": personal.get("Height") or None,
            "weight": personal.get("Weight") or None,
            "photo": m.group(1) if m else None,
            "charges": self._parse_charges(tree),
            "personal": personal,
        }

    def _parse_charges(self, tree) -> list[Charge]:
        ctable = None
        for t in tree.css("table"):
            head = t.css_first("thead")
            if head is None:
                continue
            htext = head.text()
            # Require the charges table's *specific* columns, not just any table mentioning
            # "Charge" — so we never latch onto an unrelated table if the page gains one.
            if "Charge" in htext and "Arrest Date" in htext and "Bond" in htext:
                ctable = t
                break
        if ctable is None:
            return []
        charges: list[Charge] = []
        for row in ctable.css("tbody tr"):
            vals = [td.text(strip=True) for td in row.css("td")]
            if not vals or not vals[0]:
                continue
            charge, arrest_date, arrest_ag, charge_ag, bond_type, bond_amt = (vals + [None] * 6)[:6]
            charges.append(
                Charge(
                    offense=charge or None,
                    disposition=None,  # jail roster: no court outcome
                    extra={
                        "arrest_date": arrest_date or None,
                        "arrest_agency": arrest_ag or None,
                        "charge_agency": charge_ag or None,
                        "bond_type": bond_type or None,
                        "bond_amount": bond_amt or None,
                    },
                )
            )
        return charges

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _surname_matches(name: str, q: str) -> bool:
        """Client-side surname filter. `name` is "SURNAME, FIRST MIDDLE"; the surname is the
        text before the first comma. Match if the query is a prefix of the whole surname or of
        any of its tokens — so "GONZALEZ" finds "ACOSTA GONZALEZ" and "SMITH" finds "SMITH-JONES".
        Both sides are punctuation-normalized (apostrophes/periods dropped, hyphens -> spaces) so
        "OBRIEN" finds "O'BRIEN" and "ST JOHN" finds "ST. JOHN". Broad on purpose (possible
        matches for human review)."""
        q = HuntAdapter._norm_surname(q)
        if not q:
            return False
        surname = HuntAdapter._norm_surname(name.split(",")[0])
        if surname.startswith(q):
            return True
        return any(tok.startswith(q) for tok in surname.split() if tok)

    @staticmethod
    def _norm_surname(s: str) -> str:
        """Upper-case, drop apostrophes/periods, treat hyphens as spaces, collapse whitespace —
        so punctuation variants of a surname compare equal (O'BRIEN ~ OBRIEN, ST. JOHN ~ ST JOHN,
        SMITH-JONES ~ SMITH JONES)."""
        s = (s or "").upper().replace("'", "").replace("’", "").replace(".", "")
        return re.sub(r"[\s\-]+", " ", s).strip()

    @staticmethod
    def _norm_sex(sex: str | None) -> str | None:
        # Unrecognized -> None (never fabricate "U"); the raw value is kept in raw.
        if not sex:
            return None
        return {"m": "M", "f": "F", "male": "M", "female": "F"}.get(sex.strip().lower())

    def _envelope(
        self,
        status: AdapterStatus,
        records: list[InmateRecord],
        total: int | None,
        start_ms: int,
        *,
        partial: bool = False,
    ) -> AdapterResult:
        return AdapterResult(
            source=self.id,
            display_name=self.display_name,
            status=status,
            records=records,
            total=total,
            partial=partial,
            duration_ms=AdapterContext.now_ms() - start_ms,
        )

    def _fail(self, status: AdapterStatus, start_ms: int, error: str | None = None) -> AdapterResult:
        return AdapterResult(
            source=self.id,
            display_name=self.display_name,
            status=status,
            duration_ms=AdapterContext.now_ms() - start_ms,
            error=error,
        )
