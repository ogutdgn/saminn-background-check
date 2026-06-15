"""Tarrant adapter — fixture-pinned tests (offline).

These feed the *real* captured Stage-1 responses through the adapter and assert the
exact normalized output. No live calls: the search test injects an httpx MockTransport
so the adapter's real code path runs against fixture bytes. Accuracy is the point —
if Tarrant changes its JSON, these break loudly instead of mis-parsing silently.
"""
from pathlib import Path

import httpx
import pytest

from adapters.base import AdapterContext, AdapterStatus, MatchType, SearchQuery
from adapters.tarrant import TarrantAdapter

FIX = Path(__file__).parent / "fixtures" / "tarrant"
LIST_MULTI = (FIX / "search_lastname-smith_multi.json").read_bytes()
LIST_NONE = (FIX / "search_no-results.json").read_bytes()
BOOKINGS = (FIX / "bookings_cid-1042590.json").read_bytes()
DETAIL = (FIX / "detail_cid-1042590.html").read_bytes()

adapter = TarrantAdapter()


def test_parse_list_maps_first_record_exactly():
    records = adapter._parse_list(LIST_MULTI)
    assert len(records) == 48
    r = records[0]  # SMITH / AARON / Black / Male / 1042590 / 6/22/1991 / Yes
    assert r.source == "tarrant"
    assert r.name == "SMITH, AARON"
    assert r.year_of_birth == "1991"          # derived from full DOB
    assert r.sex == "M"                         # normalized "Male" -> "M"
    assert r.source_url.endswith("CID=1042590")
    assert r.raw["DOB"] == "6/22/1991"          # full DOB preserved verbatim
    assert r.raw["CID"] == "1042590"
    # list level carries no charges/photo (lazy N+1 hydration)
    assert r.charges == [] and r.photo_base64 is None
    # Tarrant searches the roster name directly -> real-name match
    assert [m.type for m in r.matched_on] == [MatchType.NAME]


def test_parse_list_no_results_is_empty():
    assert adapter._parse_list(LIST_NONE) == []


def test_parse_bookings_to_charges():
    charges = adapter._parse_bookings(BOOKINGS)
    assert len(charges) == 2
    c = charges[0]
    assert c.offense == "CRIMINAL TRESPASS"
    assert c.case_no == "1921030"
    assert c.disposition is None               # jail roster has no court disposition
    assert c.extra["BondAmount"] == "$500.00"  # source-specific kept in extra
    assert c.extra["BookInDate"] == "5/15/2026"


def test_extract_mugshot_returns_base64_jpeg():
    photo = adapter._extract_mugshot(DETAIL)
    assert photo is not None
    assert photo.startswith("/9j/")            # JPEG magic in base64
    assert len(photo) > 1000


@pytest.mark.asyncio
async def test_search_returns_ok_with_records():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "GetSearchResults" in str(request.url)
        return httpx.Response(200, content=LIST_MULTI)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        res = await adapter.search(SearchQuery(last="smith"), AdapterContext(client))
    assert res.status == AdapterStatus.OK
    assert res.source == "tarrant" and res.display_name == "Tarrant County"
    assert len(res.records) == 48 and res.total == 48
    assert res.duration_ms >= 0


@pytest.mark.asyncio
async def test_search_no_results_status():
    async def run():
        def handler(request):
            return httpx.Response(200, content=LIST_NONE)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await adapter.search(SearchQuery(last="zzqxwv"), AdapterContext(client))

    res = await run()
    assert res.status == AdapterStatus.NO_RESULTS
    assert res.records == [] and res.total == 0


@pytest.mark.asyncio
async def test_search_converts_transport_error_to_error_status():
    def handler(request):
        raise httpx.ConnectError("boom")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        res = await adapter.search(SearchQuery(last="smith"), AdapterContext(client))
    # never raises out of search() — failure becomes an ERROR result
    assert res.status == AdapterStatus.ERROR
    assert res.error and "boom" in res.error
