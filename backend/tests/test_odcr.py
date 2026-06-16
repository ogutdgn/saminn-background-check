"""ODCR (Oklahoma statewide) adapter — fixture-pinned tests (offline).

ODCR is HTML (a statewide court-case index). These pin the results-table parsing, the
one-record-per-case rule, the "Offense or Cause" -> offense/disposition split (with the
full text preserved), the server result count, the "0 results" signal, and the full
POST-redirect-GET session + pagination flow via MockTransport.
"""
from pathlib import Path

import httpx
import pytest

from adapters.base import AdapterContext, AdapterStatus, MatchType, SearchQuery
from adapters.odcr import OdcrAdapter

FIX = Path(__file__).parent / "fixtures" / "odcr"
PAGE1 = (FIX / "search_smithjohn_page1.html").read_bytes()
PAGE2 = (FIX / "search_smithjohn_page2.html").read_bytes()
NONE = (FIX / "search_no-results.html").read_bytes()
DETAIL = (FIX / "detail_atoka_cm0500249.html").read_bytes()

adapter = OdcrAdapter()
adapter.page_delay_s = 0  # no politeness sleeps in tests


# -- pure parsing ---------------------------------------------------------

def test_one_record_per_case_row_no_grouping():
    records = adapter._parse_rows(PAGE1.decode("utf-8", "replace"))
    assert len(records) == 15                       # 15 result rows -> 15 records (no grouping)
    assert all(len(r.charges) == 1 for r in records)
    assert all(r.source == "odcr" for r in records)
    # ODCR is a pure court index: no biographical identity data, no mugshots — anywhere.
    assert all(r.year_of_birth is None for r in records)
    assert all(r.sex is None for r in records)
    assert all(r.photo_base64 is None for r in records)


def test_field_mapping_offense_disposition_and_link():
    records = adapter._parse_rows(PAGE1.decode("utf-8", "replace"))
    r = records[0]
    assert r.name == "SMITH, JOHN"
    assert [(m.type, m.detail) for m in r.matched_on] == [(MatchType.NAME, "Defendant")]
    assert r.source_url == "https://odcr.com/detail?court=003-&casekey=003-CM++0500249"
    c = r.charges[0]
    assert c.case_no == "CM-2005-00249"
    assert c.extra["court"] == "Atoka"
    assert c.extra["filed"] == "11/14/2005"
    # "BEING DRUNK IN A PUBLIC PLACE - ST GUILTY PLEA" -> offense / disposition split…
    assert c.offense == "BEING DRUNK IN A PUBLIC PLACE"
    assert c.disposition == "GUILTY PLEA"
    # …with the full original text never lost
    assert c.extra["offense_or_cause"] == "BEING DRUNK IN A PUBLIC PLACE - ST GUILTY PLEA"
    # stable identity for dedup / deep link: court code + space-decoded casekey
    assert r.raw["court_code"] == "003-"
    assert r.raw["casekey"] == "003-CM  0500249"
    # detail_id packs court + casekey so the UI can pull the full case sheet
    assert r.raw["detail_id"] == "003-::003-CM  0500249"


def test_offense_split_edges():
    split = adapter._split_offense
    assert split("INDEBTEDNESS - ST REMOVED TO FEDERAL COURT") == ("INDEBTEDNESS", "REMOVED TO FEDERAL COURT")
    assert split("FORCIBLE ENTRY - $0-$5000 - ST NON-JURY TRIAL") == ("FORCIBLE ENTRY - $0-$5000", "NON-JURY TRIAL")
    assert split("MARRIAGE LICENSE") == ("MARRIAGE LICENSE", None)  # no delimiter -> all offense
    assert split("") == (None, None)
    assert split(None) == (None, None)


def test_result_count_and_no_results_signal():
    assert adapter._result_count(PAGE1.decode("utf-8", "replace")) == 1000   # "Limited to 1,000 results"
    none = NONE.decode("utf-8", "replace")
    assert adapter._result_count(none) == 0
    assert adapter._is_no_results(none, 0) is True
    assert adapter._parse_rows(none) == []                                   # no rows on a 0-results page


# -- full flow via MockTransport -----------------------------------------

@pytest.mark.asyncio
async def test_search_runs_full_session_flow():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}")
        if request.url.path == "/search":
            return httpx.Response(200, content=PAGE1)   # POST 302 -> /results page1 (followed)
        return httpx.Response(200, content=b"<html></html>")  # GET /

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        res = await adapter.search(SearchQuery(last="smith", first="john", max_results=5), AdapterContext(client))

    assert res.status == AdapterStatus.OK
    assert res.source == "odcr" and res.display_name == "Oklahoma (ODCR)"
    assert res.total == 1000 and res.records
    # proves it walked the flow: GET / for the cookie, then POST /search
    assert "GET /" in seen
    assert "POST /search" in seen


@pytest.mark.asyncio
async def test_search_sends_party_last_comma_first_and_party_type():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search":
            from urllib.parse import parse_qs
            captured.update({k: v[0] for k, v in
                             parse_qs(request.content.decode(), keep_blank_values=True).items()})
            return httpx.Response(200, content=PAGE1)
        return httpx.Response(200, content=b"<html></html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await adapter.search(SearchQuery(last="Smith", first="John", max_results=5), AdapterContext(client))

    assert captured["party"] == "SMITH, JOHN"     # "LAST, FIRST", upper-cased
    assert captured["party-type"] == "P+D"        # parties (defendants/plaintiffs), never attorneys
    assert captured["court"] == ""                # statewide; we rank client-side


@pytest.mark.asyncio
async def test_search_no_results_status():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search":
            return httpx.Response(200, content=NONE)
        return httpx.Response(200, content=b"<html></html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        res = await adapter.search(SearchQuery(last="zzqxwvnoexist"), AdapterContext(client))

    assert res.status == AdapterStatus.NO_RESULTS
    assert res.records == []
    assert res.total == 0


@pytest.mark.asyncio
async def test_pagination_accumulates_across_pages_and_dedups():
    # POST /search -> page1; GET /results?page=2 -> page2; GET /results?page=3 -> page2 again
    # (a repeat = the dedup stop signal, like Dallas).
    paging_pages = [PAGE2, PAGE2]
    calls = {"results": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if p == "/search":
            return httpx.Response(200, content=PAGE1)
        if p == "/results":
            i = calls["results"]
            calls["results"] += 1
            return httpx.Response(200, content=paging_pages[min(i, len(paging_pages) - 1)])
        return httpx.Response(200, content=b"<html></html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        res = await adapter.search(SearchQuery(last="smith", first="john", max_results=100), AdapterContext(client))

    assert res.status == AdapterStatus.OK
    assert res.partial is False                       # reached the end via dedup, not capped
    assert len(res.records) == 30                     # 15 + 15 distinct rows across two pages
    assert {r.raw["page"] for r in res.records} == {1, 2}
    assert calls["results"] == 2                      # fetched page2, then page3 (the repeat) and stopped


@pytest.mark.asyncio
async def test_returns_full_result_set_ignoring_max_results():
    # ODCR is the statewide net: it returns ALL results (up to the server's 1,000 cap), NOT just
    # query.max_results. A tiny max_results must not cap it — it pages until the end.
    calls = {"results": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search":
            return httpx.Response(200, content=PAGE1)
        if request.url.path == "/results":
            calls["results"] += 1
            return httpx.Response(200, content=PAGE2)   # page2, then page2 again (dedup end)
        return httpx.Response(200, content=b"<html></html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        res = await adapter.search(SearchQuery(last="smith", max_results=5), AdapterContext(client))

    assert res.status == AdapterStatus.OK
    assert len(res.records) == 30          # 30 distinct across two pages — NOT capped at 5
    assert res.partial is False            # reached the true end (dedup), nothing dropped
    assert calls["results"] == 2           # fetched page2, then the repeat, then stopped


@pytest.mark.asyncio
async def test_pagination_stops_at_time_budget_partial():
    calls = {"results": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search":
            return httpx.Response(200, content=PAGE1)
        if request.url.path == "/results":
            calls["results"] += 1
            return httpx.Response(200, content=PAGE2)
        return httpx.Response(200, content=b"<html></html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        # timeout_s=0 -> deadline is "now"; tripped right after page 1
        res = await adapter.search(
            SearchQuery(last="smith", max_results=1000), AdapterContext(client, timeout_s=0.0)
        )

    assert res.status == AdapterStatus.OK
    assert res.partial is True                        # capped by the time budget
    assert len(res.records) == 15                     # only page 1 gathered
    assert calls["results"] == 0                      # stopped before fetching the next page


@pytest.mark.asyncio
async def test_search_error_is_isolated_not_raised():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        res = await adapter.search(SearchQuery(last="smith"), AdapterContext(client))

    assert res.status == AdapterStatus.ERROR        # never raises out of search()
    assert res.records == [] and res.error


@pytest.mark.asyncio
async def test_search_timeout_status():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        res = await adapter.search(SearchQuery(last="smith"), AdapterContext(client))

    assert res.status == AdapterStatus.TIMEOUT      # the 4th outcome (was untested)


# -- fetch_detail (the full case sheet) ----------------------------------

def test_parse_detail_builds_case_sheet():
    d = adapter._parse_detail(DETAIL.decode("utf-8", "replace"))
    assert d["case_no"] == "CM-2005-00249"
    assert d["court_name"] == "Atoka"
    assert d["case_type"] == "Criminal Misdemeanor Proceedings"
    assert d["filed"] == "11/14/2005"
    assert d["offense"] == "BEING DRUNK IN A PUBLIC PLACE" and d["disposition"] == "GUILTY PLEA"
    assert d["parties"]["Defendant"] == "SMITH, JOHN"
    assert d["parties"]["Judge"] == "MERRIOTT, NEAL"
    assert len(d["docket"]) >= 8                       # real dated docket events
    assert all("Grand Total" not in date for date, _ in d["docket"])  # footer row dropped
    sheet = d["sheet"]
    assert "CASE INFORMATION" in sheet and "PARTIES INVOLVED" in sheet and "CASE ENTRIES" in sheet
    assert "STATE OF OKLAHOMA VS. SMITH, JOHN" in sheet


@pytest.mark.asyncio
async def test_fetch_detail_returns_record_with_sheet():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/detail":
            # the casekey's spaces survive the round-trip through the detail_id
            assert request.url.params.get("court") == "003-"
            assert request.url.params.get("casekey") == "003-CM  0500249"
            return httpx.Response(200, content=DETAIL)
        return httpx.Response(200, content=b"<html></html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rec = await adapter.fetch_detail("003-::003-CM  0500249", AdapterContext(client))

    assert rec is not None
    assert rec.source == "odcr"
    assert rec.charges and rec.charges[0].case_no == "CM-2005-00249"
    assert rec.charges[0].disposition == "GUILTY PLEA"
    assert rec.raw["parties"]["Defendant"] == "SMITH, JOHN"
    assert "CASE ENTRIES" in (rec.raw.get("detail_text") or "")


@pytest.mark.asyncio
async def test_fetch_detail_bad_id_returns_none():
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, content=b"<html></html>"))) as client:
        assert await adapter.fetch_detail("no-separator-here", AdapterContext(client)) is None
