"""Denton County adapter — fixture-pinned tests (offline).

Denton is Tier-3 Tyler "Public Access" (stateful ASP.NET WebForms). These pin the
results-row parsing (name + birth-year split, disposition, charge, CaseID), the record
count + no-results signal, and the full GET → node POST → search POST flow via
MockTransport — asserting the load-bearing magic fields (BaseConnKy=DF etc.) are sent.
"""
from pathlib import Path

import httpx
import pytest

from adapters.base import AdapterContext, AdapterStatus, MatchType, SearchQuery
from adapters.denton import DentonAdapter

FIX = Path(__file__).parent / "fixtures" / "denton"
FORM = (FIX / "00_search_form_ID100.html").read_bytes()           # stands in for the node-aware form
MULTI = (FIX / "results_smith_multi.html").read_bytes()           # 400 records
NONE = (FIX / "results_no-results.html").read_bytes()             # 0 records

adapter = DentonAdapter()


# -- pure parsing ---------------------------------------------------------

def test_parse_results_one_record_per_case():
    recs = adapter._parse_results(MULTI.decode("utf-8", "replace"))
    assert len(recs) == 400
    assert adapter._record_count(MULTI.decode("utf-8", "replace")) == 400
    assert all(r.source == "denton" for r in recs)
    assert all(len(r.charges) == 1 for r in recs)
    assert all(r.sex is None and r.photo_base64 is None for r in recs)   # court records, no sex/photo
    assert all(r.raw["detail_id"] for r in recs)                          # CaseID present


def test_field_mapping_name_dob_charge_disposition():
    r = adapter._parse_results(MULTI.decode("utf-8", "replace"))[0]
    assert r.name == "Smith, James Robert"
    assert r.year_of_birth == "1972"                 # year of the list DOB (full birthdate not retained)
    assert [(m.type, m.detail) for m in r.matched_on] == [(MatchType.NAME, "Defendant")]
    assert r.source_url == "https://justice1.dentoncounty.gov/PublicAccess/CaseDetail.aspx?CaseID=649089"
    assert r.raw["detail_id"] == "649089"
    c = r.charges[0]
    assert c.case_no == "00-0151J5"
    assert c.disposition == "z-Traffic Citation Disposed"
    assert "SPEEDING" in (c.offense or "")
    assert c.extra["citation"] == "A902776"
    assert "Justice of the Peace" in (c.extra["court"] or "")
    assert c.extra["filed"] == "01/19/2000"


def test_split_name_dob_and_filed_loc():
    assert adapter._split_name_dob("Smith, James Robert 03/17/1972") == ("Smith, James Robert", "1972")
    assert adapter._split_name_dob("Doe, Jane") == ("Doe, Jane", None)      # no DOB -> year None
    assert adapter._split_filed_loc("01/19/2000 Justice of the Peace Pct #5 Gailey, Barbara") == (
        "01/19/2000", "Justice of the Peace Pct #5 Gailey, Barbara")


def test_no_results_signal():
    text = NONE.decode("utf-8", "replace")
    assert adapter._record_count(text) == 0
    assert adapter._parse_results(text) == []


# -- full flow via MockTransport -----------------------------------------

def _client(results: bytes):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/default.aspx"):
            return httpx.Response(200, content=b"<html></html>")
        if request.method == "POST" and request.url.path.endswith("/Search.aspx"):
            body = request.content.decode()
            if "LastName" in body and "SearchSubmit" in body:        # the real search POST
                from urllib.parse import parse_qs
                captured.update({k: v[0] for k, v in parse_qs(body, keep_blank_values=True).items()})
                return httpx.Response(200, content=results)
            return httpx.Response(200, content=FORM)                  # the node-establishing POST
        return httpx.Response(200, content=b"<html></html>")

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), captured


@pytest.mark.asyncio
async def test_search_full_flow_sends_magic_fields():
    client, captured = _client(MULTI)
    async with client:
        res = await adapter.search(SearchQuery(last="Smith"), AdapterContext(client))
    assert res.status == AdapterStatus.OK
    assert res.source == "denton" and res.total == 400
    assert res.partial is True                       # capped at the Tyler 400 limit
    assert len(res.records) == 400
    # the load-bearing magic fields for a party-name (defendant) search
    assert captured["SearchBy"] == "1" and captured["SearchType"] == "PARTY"
    assert captured["SearchMode"] == "NAME" and captured["NameTypeKy"] == "ALIAS"
    assert captured["BaseConnKy"] == "DF"            # <- the field that makes it return defendants
    assert captured["LastName"] == "Smith"
    assert captured["AllStatusTypes"] == "true" and captured["SortBy"] == "casenumber"


@pytest.mark.asyncio
async def test_search_no_results_status():
    client, _ = _client(NONE)
    async with client:
        res = await adapter.search(SearchQuery(last="zzqxnope"), AdapterContext(client))
    assert res.status == AdapterStatus.NO_RESULTS
    assert res.records == [] and res.total == 0


@pytest.mark.asyncio
async def test_search_timeout_status():
    def handler(request):
        raise httpx.TimeoutException("slow")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        res = await adapter.search(SearchQuery(last="smith"), AdapterContext(client))
    assert res.status == AdapterStatus.TIMEOUT


@pytest.mark.asyncio
async def test_search_error_is_isolated():
    def handler(request):
        raise httpx.ConnectError("down")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        res = await adapter.search(SearchQuery(last="smith"), AdapterContext(client))
    assert res.status == AdapterStatus.ERROR and res.error      # never raises out of search()
