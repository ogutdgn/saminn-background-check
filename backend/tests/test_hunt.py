"""Hunt County adapter — fixture-pinned tests (offline).

Hunt has NO server-side name search: results.asp returns the whole current roster and the
adapter filters by surname client-side. These pin the roster parsing, the surname filter
(prefix + compound/hyphenated tokens), the OK / no-match / capped / error outcomes, and the
booking.asp detail parse (mugshot + charges + personal details). Deterministic cases use a
synthetic roster; two smoke tests run the real captured fixtures.
"""
from pathlib import Path

import httpx
import pytest

from adapters.base import AdapterContext, AdapterStatus, MatchType, SearchQuery
from adapters.hunt import HuntAdapter
from selectolax.parser import HTMLParser

FIX = Path(__file__).parent / "fixtures" / "hunt"
REAL_ROSTER = (FIX / "roster_current.html").read_bytes()
REAL_BOOKING = (FIX / "booking_174728.html").read_bytes()

adapter = HuntAdapter()


def _roster(*rows: tuple) -> str:
    """Build a #bookings roster page. Each row: (name, party, jail, gender, race, booking, released)."""
    thead = ("<thead><tr><th>Name</th><th>Gender</th><th>Race</th>"
             "<th>Booking Date</th><th>Released Date</th></tr></thead>")
    body = ""
    for name, party, jail, gender, race, booking, released in rows:
        body += (f'<tr><th data-released="{released}" data-party="{party}" data-jailid="{jail}" '
                 f'scope="row">{name}</th><td>{gender}</td><td>{race}</td>'
                 f'<td>{booking}</td><td>{released}</td></tr>')
    return f'<html><body><table id="bookings">{thead}<tbody>{body}</tbody></table></body></html>'


SAMPLE = _roster(
    ("ACOSTA GONZALEZ, ENRIQUE", "1185419", "174728", "M", "W", "5/17/2026", ""),
    ("SMITH-JONES, MARIA", "222", "333", "F", "B", "6/1/2026", ""),
    ("ANDERSON, KHIRY DRAYON", "40820", "174905", "M", "B", "6/3/2026", ""),
    ("GONZALEZ, PEDRO", "555", "666", "M", "W", "6/4/2026", ""),
)


# -- pure parsing / filtering --------------------------------------------

def test_parse_roster_field_mapping():
    table = HTMLParser(SAMPLE).css_first("#bookings")
    recs = adapter._parse_roster(table)
    assert len(recs) == 4
    r = recs[0]
    assert r.source == "hunt"
    assert r.name == "ACOSTA GONZALEZ, ENRIQUE"
    assert r.sex == "M"
    assert r.booking_date == "5/17/2026"
    assert r.raw["race"] == "W"
    assert r.raw["detail_id"] == "1185419-174728"   # "<party>-<jail>" -> fetch_detail / UI photo
    assert r.year_of_birth is None                  # Hunt has no DOB anywhere
    assert r.photo_base64 is None                   # photo only via fetch_detail
    assert [m.type for m in r.matched_on] == [MatchType.NAME]


def test_surname_filter_prefix_and_compound_tokens():
    m = adapter._surname_matches
    assert m("GONZALEZ, PEDRO", "GONZALEZ") is True
    assert m("ACOSTA GONZALEZ, ENRIQUE", "GONZALEZ") is True   # token of a compound surname
    assert m("ACOSTA GONZALEZ, ENRIQUE", "ACOSTA") is True     # first token
    assert m("SMITH-JONES, MARIA", "SMITH") is True            # hyphenated
    assert m("SMITH-JONES, MARIA", "JONES") is True
    assert m("ANDERSON, KHIRY", "AND") is True                 # prefix
    assert m("ANDERSON, KHIRY", "SON") is False                # not a prefix of any token
    assert m("GONZALEZ, PEDRO", "") is False                   # empty query never matches


# -- search() via MockTransport ------------------------------------------

def _client(roster_html: bytes | str, booking_html: bytes | str = b"ok"):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/results.asp"):
            return httpx.Response(200, content=roster_html if isinstance(roster_html, bytes)
                                  else roster_html.encode())
        if request.url.path.endswith("/booking.asp"):
            return httpx.Response(200, content=booking_html if isinstance(booking_html, bytes)
                                  else booking_html.encode())
        return httpx.Response(200, content=b"ok")
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_search_filters_roster_by_surname():
    async with _client(SAMPLE) as client:
        res = await adapter.search(SearchQuery(last="gonzalez"), AdapterContext(client))
    assert res.status == AdapterStatus.OK
    assert res.source == "hunt" and res.display_name == "Hunt County"
    # GONZALEZ matches "GONZALEZ, PEDRO" and the compound "ACOSTA GONZALEZ, ENRIQUE"
    assert {r.name for r in res.records} == {"GONZALEZ, PEDRO", "ACOSTA GONZALEZ, ENRIQUE"}
    assert res.total == 2 and res.partial is False
    assert all(m.type == MatchType.NAME for r in res.records for m in r.matched_on)


@pytest.mark.asyncio
async def test_search_no_surname_match_is_no_results():
    async with _client(SAMPLE) as client:
        res = await adapter.search(SearchQuery(last="ZZQXNOPE"), AdapterContext(client))
    assert res.status == AdapterStatus.NO_RESULTS
    assert res.records == [] and res.total == 0


@pytest.mark.asyncio
async def test_search_caps_at_max_results_and_marks_partial():
    big = _roster(*[(f"SMITH, PERSON {i}", str(i), str(1000 + i), "M", "W", "6/1/2026", "")
                    for i in range(10)])
    async with _client(big) as client:
        res = await adapter.search(SearchQuery(last="SMITH", max_results=3), AdapterContext(client))
    assert res.status == AdapterStatus.OK
    assert len(res.records) == 3        # capped
    assert res.total == 10              # but the true match count is reported
    assert res.partial is True


@pytest.mark.asyncio
async def test_search_missing_table_is_error_not_silent():
    async with _client("<html><body>maintenance</body></html>") as client:
        res = await adapter.search(SearchQuery(last="SMITH"), AdapterContext(client))
    assert res.status == AdapterStatus.ERROR     # fail loud, never silent bad data
    assert res.records == [] and res.error


@pytest.mark.asyncio
async def test_search_connect_error_is_isolated():
    def handler(request):
        raise httpx.ConnectError("down")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        res = await adapter.search(SearchQuery(last="SMITH"), AdapterContext(client))
    assert res.status == AdapterStatus.ERROR     # never raises out of search()


# -- fetch_detail() ------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_detail_parses_mugshot_charges_personal():
    async with _client(SAMPLE, booking_html=REAL_BOOKING) as client:
        rec = await adapter.fetch_detail("1185419-174728", AdapterContext(client))
    assert rec is not None
    assert rec.source == "hunt"
    assert rec.name == "ACOSTA GONZALEZ, ENRIQUE"
    assert rec.sex == "M"
    assert rec.raw["race"] == "W"
    assert rec.photo_base64 and len(rec.photo_base64) > 1000     # real base64 mugshot
    assert len(rec.charges) == 3
    offenses = [c.offense for c in rec.charges]
    assert "DRIVING WHILE INTOXICATED 2ND" in offenses
    c0 = rec.charges[0]
    assert c0.extra["bond_type"] == "SUR" and c0.extra["bond_amount"] == "3000.00"
    assert c0.extra["arrest_agency"] == "DPS"
    assert c0.disposition is None                                 # jail roster: no court outcome


@pytest.mark.asyncio
async def test_fetch_detail_invalid_form_returns_none():
    invalid = b"<html><body><div class='alert alert-danger'>Invalid Form Sent</div></body></html>"
    async with _client(SAMPLE, booking_html=invalid) as client:
        rec = await adapter.fetch_detail("1-2", AdapterContext(client))
    assert rec is None


@pytest.mark.asyncio
async def test_fetch_detail_bad_id_returns_none():
    async with _client(SAMPLE) as client:
        rec = await adapter.fetch_detail("noseparator", AdapterContext(client))
    assert rec is None


# -- smoke tests against the real captured fixtures ----------------------

def test_real_roster_capture_parses():
    table = HTMLParser(REAL_ROSTER.decode("utf-8", "replace")).css_first("#bookings")
    recs = adapter._parse_roster(table)
    assert len(recs) > 50                                # a county jail always holds dozens
    assert all(r.name and r.raw["detail_id"] for r in recs)
    assert all("-" in r.raw["detail_id"] for r in recs)  # "<party>-<jail>"
    # filtering by the first inmate's own surname finds at least that inmate
    surname = recs[0].name.split(",")[0].split()[0]
    assert any(adapter._surname_matches(r.name, surname.upper()) for r in recs)


def test_real_booking_capture_parses():
    d = adapter._parse_booking(REAL_BOOKING.decode("utf-8", "replace"))
    assert d["name"] == "ACOSTA GONZALEZ, ENRIQUE"
    assert d["sex"] == "M" and d["race"] == "W"
    assert d["photo"] and len(d["photo"]) > 1000
    assert len(d["charges"]) == 3


# -- review-driven hardening (adversarial review, 2026-06-15) -------------

@pytest.mark.asyncio
async def test_search_timeout_status():
    def handler(request):
        raise httpx.TimeoutException("slow")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        res = await adapter.search(SearchQuery(last="SMITH"), AdapterContext(client))
    assert res.status == AdapterStatus.TIMEOUT      # the 4th outcome (was untested)


@pytest.mark.asyncio
async def test_capped_roster_marks_partial_even_on_no_match():
    # If the roster hit the server LIMIT it was truncated -> a no-match is uncertain (a match
    # could lie past the cap), and a match set is also incomplete. Both must be `partial`.
    capped = HuntAdapter()
    capped.LIMIT = 3
    roster3 = _roster(
        ("ALPHA, A", "1", "11", "M", "W", "6/1/2026", ""),
        ("BRAVO, B", "2", "22", "M", "W", "6/1/2026", ""),
        ("CHARLIE, C", "3", "33", "F", "B", "6/1/2026", ""),
    )
    async with _client(roster3) as client:
        none = await capped.search(SearchQuery(last="ZZNOPE"), AdapterContext(client))
        some = await capped.search(SearchQuery(last="ALPHA"), AdapterContext(client))
    assert none.status == AdapterStatus.NO_RESULTS and none.partial is True
    assert some.status == AdapterStatus.OK and some.partial is True


@pytest.mark.asyncio
async def test_fetch_detail_empty_name_returns_none():
    # A booking page whose Personal Details carries no Last Name -> no identity -> None (fail loud,
    # never return an empty-named record).
    booking = ("<html><body>"
               "<div class='form-group'><label>Last Name</label><input value='' /></div>"
               "<div class='form-group'><label>First Name</label><input value='' /></div>"
               "<div class='form-group'><label>Sex</label><input value='M' /></div>"
               "</body></html>")
    async with _client(SAMPLE, booking_html=booking) as client:
        rec = await adapter.fetch_detail("1-2", AdapterContext(client))
    assert rec is None


def test_surname_filter_handles_apostrophes_and_periods():
    m = adapter._surname_matches
    assert m("O'BRIEN, SEAN", "OBRIEN") is True        # typed without the apostrophe
    assert m("O'BRIEN, SEAN", "O'BRIEN") is True
    assert m("ST. JOHN, MARY", "ST JOHN") is True      # period dropped, whitespace normalized
    assert m("ST. JOHN, MARY", "JOHN") is True         # later token still matches
