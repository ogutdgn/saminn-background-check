"""Denton County District Court adapter — fixture-pinned tests (offline).

DentonDCAdapter is the felony counterpart to DentonAdapter (misdemeanors). The parsers are
identical — only the host sub-path (/PublicAccessDC/), search ID (100 = Criminal), and
NodeID list differ. These tests pin the parsing logic and verify the flow sends the correct
URL and magic fields.
"""
import httpx
import pytest

from adapters.base import AdapterContext, AdapterStatus, MatchType, SearchQuery
from adapters.denton_dc import DentonDCAdapter

adapter = DentonDCAdapter()

# Minimal synthetic HTML that mirrors the real Denton DC results page structure.
_RESULTS_HTML = b"""
<html><body>
<span>Record Count: <b>2</b></span>
<table>
<tr><th>Case No</th><th>Citation</th><th>Defendant Info</th><th>Filed/Location</th><th>Type/Status</th><th>Charge(s)</th></tr>
<tr>
  <td><a href="CaseDetail.aspx?CaseID=111111">F22-1234-158</a></td>
  <td></td>
  <td>Smith, John Allen 05/10/1985</td>
  <td>01/15/2022 158th Judicial District Court Burgess, Steve</td>
  <td>Felony by Indictment Active: Pre-Trial</td>
  <td>POSSESSION OF CONTROLLED SUBSTANCE PG1 &gt;=1G&lt;4G</td>
</tr>
<tr>
  <td><a href="CaseDetail.aspx?CaseID=222222">F21-9876-211</a></td>
  <td></td>
  <td>Smith, Maria Luisa 03/22/1990</td>
  <td>08/30/2021 211th Judicial District Court Shanklin, Brody</td>
  <td>Felony by Information Inactive: Disposed</td>
  <td>THEFT OF PROPERTY &gt;=$2,500&lt;$30,000</td>
</tr>
</table>
</body></html>
"""

_NO_RESULTS_HTML = b"""
<html><body>
<span>Record Count: <b>0</b></span>
<table><tr><td>No cases matched your search criteria.</td></tr></table>
</body></html>
"""

_FORM_HTML = b"""
<html><body>
<form id="SearchParameters" method="post">
<input type="hidden" name="__VIEWSTATE" value="FAKEVIEWSTATE" />
<input type="hidden" name="__VIEWSTATEGENERATOR" value="FAKEVSG" />
<input type="hidden" name="__EVENTVALIDATION" value="FAKEEV" />
<input type="hidden" name="NodeID" value="" />
<input type="hidden" name="SearchType" value="" />
<input type="hidden" name="SearchMode" value="" />
<input type="hidden" name="NameTypeKy" value="" />
<input type="hidden" name="BaseConnKy" value="" />
<input type="hidden" name="StatusType" value="" />
<input type="hidden" name="ShowInactive" value="" />
<input type="hidden" name="AllStatusTypes" value="" />
<input type="hidden" name="RequireFirstName" value="" />
<select name="SortBy"><option value="casenumber">Case Number</option></select>
<input type="submit" name="SearchSubmit" value="Search" />
</form>
</body></html>
"""

_HOST = "https://justice1.dentoncounty.gov/PublicAccessDC"


# -- pure parsing ----------------------------------------------------------

def test_parse_results_returns_one_record_per_case():
    recs = adapter._parse_results(_RESULTS_HTML.decode())
    assert len(recs) == 2
    assert all(r.source == "denton_dc" for r in recs)
    assert all(len(r.charges) == 1 for r in recs)
    assert all(r.sex is None and r.photo_base64 is None for r in recs)


def test_field_mapping_first_record():
    r = adapter._parse_results(_RESULTS_HTML.decode())[0]
    assert r.name == "Smith, John Allen"
    assert r.year_of_birth == "1985"
    assert r.source_url == f"{_HOST}/CaseDetail.aspx?CaseID=111111"
    assert r.raw["detail_id"] == "111111"
    assert r.raw["case_no"] == "F22-1234-158"
    assert [(m.type, m.detail) for m in r.matched_on] == [(MatchType.NAME, "Defendant")]
    c = r.charges[0]
    assert c.case_no == "F22-1234-158"
    assert "POSSESSION" in (c.offense or "")
    assert "Felony by Indictment" in (c.disposition or "")
    assert c.extra["filed"] == "01/15/2022"
    assert "158th Judicial District Court" in (c.extra["court"] or "")


def test_field_mapping_second_record():
    r = adapter._parse_results(_RESULTS_HTML.decode())[1]
    assert r.name == "Smith, Maria Luisa"
    assert r.year_of_birth == "1990"
    assert r.raw["detail_id"] == "222222"
    assert "THEFT" in (r.charges[0].offense or "")
    assert "Felony by Information" in (r.charges[0].disposition or "")


def test_record_count():
    assert adapter._record_count(_RESULTS_HTML.decode()) == 2
    assert adapter._record_count(_NO_RESULTS_HTML.decode()) == 0


def test_no_results_returns_empty():
    assert adapter._parse_results(_NO_RESULTS_HTML.decode()) == []


def test_split_name_dob_with_dob():
    assert adapter._split_name_dob("Smith, John Allen 05/10/1985") == ("Smith, John Allen", "1985")


def test_split_name_dob_without_dob():
    assert adapter._split_name_dob("Doe, Jane") == ("Doe, Jane", None)


def test_split_filed_loc_with_date():
    name, court = adapter._split_filed_loc("01/15/2022 158th Judicial District Court Burgess, Steve")
    assert name == "01/15/2022"
    assert court == "158th Judicial District Court Burgess, Steve"


def test_split_filed_loc_no_date():
    name, court = adapter._split_filed_loc("some court info")
    assert name is None
    assert court == "some court info"


# -- full flow via MockTransport ------------------------------------------

def _make_client(results: bytes):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, content=b"<html></html>")
        body = request.content.decode()
        if "LastName" in body and "SearchSubmit" in body:
            from urllib.parse import parse_qs
            captured.update({k: v[0] for k, v in parse_qs(body, keep_blank_values=True).items()})
            captured["_url"] = str(request.url)
            return httpx.Response(200, content=results)
        return httpx.Response(200, content=_FORM_HTML)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), captured


@pytest.mark.asyncio
async def test_search_sends_correct_url_and_magic_fields():
    client, captured = _make_client(_RESULTS_HTML)
    async with client:
        res = await adapter.search(SearchQuery(last="Smith"), AdapterContext(client))
    assert res.status == AdapterStatus.OK
    assert res.source == "denton_dc"
    assert res.total == 2
    assert len(res.records) == 2
    assert res.partial is False
    # Correct endpoint
    assert "PublicAccessDC" in captured["_url"]
    assert "ID=100" in captured["_url"]
    # Magic fields
    assert captured["SearchBy"] == "1"
    assert captured["SearchType"] == "PARTY"
    assert captured["SearchMode"] == "NAME"
    assert captured["NameTypeKy"] == "ALIAS"
    assert captured["BaseConnKy"] == "DF"
    assert captured["LastName"] == "Smith"
    assert captured["AllStatusTypes"] == "true"
    assert captured["SortBy"] == "casenumber"


@pytest.mark.asyncio
async def test_search_no_results_status():
    client, _ = _make_client(_NO_RESULTS_HTML)
    async with client:
        res = await adapter.search(SearchQuery(last="zzqxnope"), AdapterContext(client))
    assert res.status == AdapterStatus.NO_RESULTS
    assert res.records == [] and res.total == 0


@pytest.mark.asyncio
async def test_search_partial_flag_when_capped():
    # partial fires when len(records) >= RESULT_CAP (400).
    # Build synthetic HTML with exactly 400 <tr> rows and record count 400.
    rows = "".join(
        f'<tr><td><a href="CaseDetail.aspx?CaseID={i}">F22-{i:04d}-158</a></td>'
        f'<td></td><td>Smith, Test{i:04d} 01/01/1990</td>'
        f'<td>01/01/2022 158th Judicial District Court Judge</td>'
        f'<td>Felony by Indictment Inactive: Disposed</td>'
        f'<td>SOME OFFENSE</td></tr>'
        for i in range(400)
    )
    cap_html = f"<html><body><span>Record Count: <b>400</b></span><table>{rows}</table></body></html>"
    client, _ = _make_client(cap_html.encode())
    async with client:
        res = await adapter.search(SearchQuery(last="Smith"), AdapterContext(client))
    assert res.partial is True
    assert len(res.records) == 400


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
    assert res.status == AdapterStatus.ERROR and res.error


@pytest.mark.asyncio
async def test_fetch_detail_returns_none_on_failure():
    def handler(request):
        raise httpx.ConnectError("down")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await adapter.fetch_detail("123456", AdapterContext(client))
    assert result is None


@pytest.mark.asyncio
async def test_fetch_detail_rejects_non_numeric_id():
    called = []
    def handler(request):
        called.append(request)
        return httpx.Response(200, content=b"<html></html>")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await adapter.fetch_detail("not-a-number", AdapterContext(client))
    assert result is None
