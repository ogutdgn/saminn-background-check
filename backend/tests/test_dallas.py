"""Dallas adapter — fixture-pinned tests (offline).

Dallas is HTML (a court-case mainframe screen). These pin the table parsing, the
per-person grouping (one person, many charges), disposition capture, the
no-results signal, and the full disclaimer-gated session flow via MockTransport.
"""
from pathlib import Path

import httpx
import pytest

from adapters.base import AdapterContext, AdapterStatus, MatchType, SearchQuery
from adapters.dallas import DallasAdapter

FIX = Path(__file__).parent / "fixtures" / "dallas"
RESULTS = (FIX / "search_lastname-smith_multi.html").read_bytes()
NONE = (FIX / "search_no-results.html").read_bytes()

adapter = DallasAdapter()


def _table(*rows: list[str]) -> str:
    """Build a minimal results page with table.table-striped and the given 9-col rows."""
    head = "<tr>" + "".join(f"<th>{h}</th>" for h in
                           ["ln", "LN", "ARC", "RS", "DOB", "CASE", "CT", "CHARGE", "DISP"]) + "</tr>"
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<html><body><table class="table table-striped">{head}{body}</table></body></html>'


def test_one_record_per_case_row_no_grouping():
    records = adapter._parse_results(RESULTS.decode("utf-8", "replace"))
    assert len(records) == 18                  # 18 charge-rows -> 18 records (no grouping)
    assert all(len(r.charges) == 1 for r in records)
    assert all(r.source == "dallas" for r in records)
    # "SMITH APRIL CHRISTINE" has 3 cases -> appears as 3 separate per-case records
    april = [r for r in records if "APRIL CHRISTINE" in r.name]
    assert len(april) == 3
    assert {r.charges[0].offense for r in april} == {"FMFR", "NDL", "SPD 42/30"}
    assert all(r.year_of_birth is None and r.raw["dob"] == "000000" for r in april)
    assert all(r.photo_base64 is None for r in april)         # court records: no mugshots


def test_row_field_mapping_and_disposition():
    records = adapter._parse_results(RESULTS.decode("utf-8", "replace"))
    rob = next(r for r in records if r.charges[0].offense == "ROB FA")  # row 01
    c = rob.charges[0]
    assert rob.name == "SMITH"
    assert [m.type for m in rob.matched_on] == [MatchType.NAME]
    assert c.case_no == "F-7211396"
    assert c.disposition == "PGBC"
    assert c.extra["court"] == "FJ"


def test_distinct_same_name_masked_dob_are_NOT_merged():
    # Regression: two DIFFERENT people, same displayed name, both masked DOB.
    # Must stay two records — never collapse one onto the other (sex/charges).
    html = _table(
        ["01", "SMITH", "", "WM", "000000", "F-111", "FJ", "ROB FA", "PGBC"],
        ["02", "SMITH", "", "BF", "000000", "F-222", "FJ", "THEFT", "DISM"],
    )
    records = adapter._parse_results(html)
    assert len(records) == 2
    assert {r.sex for r in records} == {"M", "F"}              # neither person's sex dropped
    assert {r.charges[0].case_no for r in records} == {"F-111", "F-222"}


def test_same_name_masked_and_unmasked_rows_are_NOT_collapsed():
    # Regression: a person whose DOB is masked on some rows and present on others
    # must not be silently split-or-merged by a DOB key — one record per case.
    html = _table(
        ["08", "SMITH JAMES DOUGLAS", "", "UU", "000000", "MC1", "MD", "FTA", "DISM"],
        ["10", "SMITH JAMES DOUGLAS", "", "WM", "092256", "MC2", "MD", "NDL", "PGBC"],
    )
    records = adapter._parse_results(html)
    assert len(records) == 2
    assert {r.raw["dob"] for r in records} == {"000000", "092256"}


def test_no_results_detected_and_empty():
    text = NONE.decode("utf-8", "replace")
    assert adapter._is_no_results(text) is True
    assert adapter._parse_results(text) == []   # no result table -> nothing parsed


@pytest.mark.asyncio
async def test_search_runs_full_session_flow():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path.endswith("/searchByName"):
            return httpx.Response(200, content=RESULTS)
        return httpx.Response(200, content=b"ok")  # disclaimer GET + captcha POST

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        res = await adapter.search(SearchQuery(last="smith"), AdapterContext(client))

    assert res.status == AdapterStatus.OK
    assert res.source == "dallas" and res.records
    # proves it walked the gate: home -> captcha -> searchByName
    assert any(p.endswith("/captcha") for p in seen)
    assert any(p.endswith("/searchByName") for p in seen)


@pytest.mark.asyncio
async def test_search_no_results_status():
    def handler(request):
        if request.url.path.endswith("/searchByName"):
            return httpx.Response(200, content=NONE)
        return httpx.Response(200, content=b"ok")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        res = await adapter.search(SearchQuery(last="zzqxwv"), AdapterContext(client))
    assert res.status == AdapterStatus.NO_RESULTS
    assert res.records == []
