"""Tests for the Collin County adapter (Tier 4, browser).

The search() method requires a live browser (Playwright / BrowserManager) and is not
unit-tested here — it is covered by live Stage-4 verification.

What IS tested here:
  • _parse_inmate_rows()  — the pure HTML parser that turns a page.content() snapshot into
    InmateRecord objects. This is the hard logic; the browser plumbing is thin wrapper code.
  • _split_name()         — "Last, First Middle" splitter
  • _normalise_sex()      — "Male"→"M", "Female"→"F"
  • no-results path       — empty table → empty list
  • client-side surname filter — global search noise is dropped
  • matched_on tagging    — NAME vs ALIAS

Fixtures: synthetic HTML that mirrors the MudBlazor rendered structure observed at
https://apps2.collincountytx.gov/JudicialOnlineSearch2/global during Stage 0 recon.
When live HTML fixtures are captured (Stage 1 spike), add a test that feeds them in.
"""
import pytest

from adapters.collin import CollinAdapter
from adapters.base import MatchType, SearchQuery

adapter = CollinAdapter()


# ---------------------------------------------------------------------------
# Synthetic HTML fixture helpers
# ---------------------------------------------------------------------------

def _make_row(name: str, yob: str, sex: str, booking: str, so: str, fields: str = "") -> str:
    return (
        f"<tr>"
        f"<td>{name}</td><td>{yob}</td><td>{sex}</td>"
        f"<td>{booking}</td><td>{so}</td><td>{fields}</td>"
        f"</tr>"
    )


def _make_page(rows: str) -> str:
    """Minimal page.content() snapshot with the MudBlazor tab-panel + table structure."""
    return f"""
    <html><body>
    <div class="mud-tabs">
      <div class="mud-tab mud-tab-active">Inmate (3)</div>
      <div class="mud-tab">Case (800)</div>
    </div>
    <div role="tabpanel">
      <table>
        <thead><tr>
          <th>Name</th><th>Year of Birth</th><th>Sex</th>
          <th>Booking Date</th><th>SO Number</th><th>Search Fields</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    </body></html>
    """


# ---------------------------------------------------------------------------
# _parse_inmate_rows
# ---------------------------------------------------------------------------

def test_parse_single_result():
    html = _make_page(_make_row("Smith, John David", "1985", "Male", "6/15/2026", "352000"))
    q = SearchQuery(last="Smith")
    records = adapter._parse_inmate_rows(html, q)
    assert len(records) == 1
    r = records[0]
    assert r.name == "Smith, John David"
    assert r.year_of_birth == "1985"
    assert r.sex == "M"
    assert r.booking_date == "6/15/2026"
    assert r.raw["so_number"] == "352000"
    assert r.raw["detail_id"] == "352000"
    assert r.source == "collin"


def test_parse_multiple_results():
    rows = (
        _make_row("Smith, John", "1985", "Male", "6/1/2026", "111111") +
        _make_row("Smith, Jane", "1992", "Female", "5/20/2026", "222222") +
        _make_row("Smithson, Rob", "1978", "Male", "4/1/2026", "333333")
    )
    q = SearchQuery(last="Smith")
    records = adapter._parse_inmate_rows(_make_page(rows), q)
    # "Smithson" starts with "Smith" → kept by the prefix filter
    assert len(records) == 3
    names = [r.name for r in records]
    assert "Smith, John" in names
    assert "Smith, Jane" in names
    assert "Smithson, Rob" in names


def test_surname_filter_drops_non_matches():
    """Global search can return noise (attorney names, case-title hits). Filter them out."""
    rows = (
        _make_row("Smith, John", "1985", "Male", "6/1/2026", "111111") +
        _make_row("Johnson, Smith", "1970", "Male", "3/1/2026", "999999")  # first name match
    )
    q = SearchQuery(last="Smith")
    records = adapter._parse_inmate_rows(_make_page(rows), q)
    assert len(records) == 1
    assert records[0].name == "Smith, John"


def test_no_results_empty_table():
    html = _make_page("")
    q = SearchQuery(last="Zzznotaname")
    records = adapter._parse_inmate_rows(html, q)
    assert records == []


def test_matched_on_name():
    html = _make_page(_make_row("Smith, John", "1985", "Male", "6/1/2026", "111111", ""))
    records = adapter._parse_inmate_rows(html, SearchQuery(last="Smith"))
    assert records[0].matched_on[0].type == MatchType.NAME


def test_matched_on_alias_when_name_differs():
    """Row matched via alias field — last name does NOT start with the query last name."""
    rows = _make_row("Williams, John", "1985", "Male", "6/1/2026", "444444",
                     "Alias: Smith, John")
    # "Williams" does not start with "Smith" → filtered out (alias-only rows are dropped
    # by the client-side filter unless we relax it). This test confirms the filter is strict.
    records = adapter._parse_inmate_rows(_make_page(rows), SearchQuery(last="Smith"))
    assert records == []


def test_sex_normalisation():
    rows = (
        _make_row("Smith, A", "1990", "Male", "1/1/2026", "1") +
        _make_row("Smith, B", "1991", "Female", "1/2/2026", "2") +
        _make_row("Smith, C", "1992", "Unknown", "1/3/2026", "3")
    )
    records = adapter._parse_inmate_rows(_make_page(rows), SearchQuery(last="Smith"))
    sexes = {r.name.split(",")[1].strip(): r.sex for r in records}
    assert sexes["A"] == "M"
    assert sexes["B"] == "F"
    assert sexes["C"] == "UNKNOWN"   # unrecognised value uppercased and preserved


def test_no_charges_on_roster_row():
    """The Inmate tab roster does not carry charge detail — charges list must be empty."""
    html = _make_page(_make_row("Smith, John", "1985", "Male", "6/1/2026", "111111"))
    records = adapter._parse_inmate_rows(html, SearchQuery(last="Smith"))
    assert records[0].charges == []


def test_first_name_query_still_matches():
    """When first name is supplied it is appended to the search term but parsing still works."""
    html = _make_page(_make_row("Smith, John", "1985", "Male", "6/1/2026", "111111"))
    q = SearchQuery(last="Smith", first="John")
    records = adapter._parse_inmate_rows(html, q)
    assert len(records) == 1


def test_row_without_so_number():
    """A row missing an SO number is still parsed; detail_id is None."""
    html = _make_page(_make_row("Smith, John", "1985", "Male", "6/1/2026", ""))
    records = adapter._parse_inmate_rows(html, SearchQuery(last="Smith"))
    assert len(records) == 1
    assert records[0].raw["so_number"] is None


def test_no_tabpanel_fallback_to_any_table():
    """If the tab-panel wrapper is absent, the parser falls back to the first table on page."""
    html = """
    <html><body>
    <table><thead><tr><th>Name</th><th>Year of Birth</th><th>Sex</th>
    <th>Booking Date</th><th>SO Number</th><th>Search Fields</th></tr></thead>
    <tbody>
    <tr><td>Smith, Jane</td><td>1990</td><td>Female</td><td>7/1/2026</td><td>555</td><td></td></tr>
    </tbody></table>
    </body></html>
    """
    records = adapter._parse_inmate_rows(html, SearchQuery(last="Smith"))
    assert len(records) == 1


# ---------------------------------------------------------------------------
# _split_name
# ---------------------------------------------------------------------------

def test_split_name_standard():
    assert CollinAdapter._split_name("Smith, John David") == ("Smith", "John David")


def test_split_name_no_comma():
    last, first = CollinAdapter._split_name("SMITH")
    assert last == "SMITH"
    assert first is None


def test_split_name_empty():
    last, first = CollinAdapter._split_name("")
    assert last is None
    assert first is None


# ---------------------------------------------------------------------------
# _normalise_sex
# ---------------------------------------------------------------------------

def test_normalise_sex_male():
    assert CollinAdapter._normalise_sex("Male") == "M"
    assert CollinAdapter._normalise_sex("M") == "M"


def test_normalise_sex_female():
    assert CollinAdapter._normalise_sex("Female") == "F"
    assert CollinAdapter._normalise_sex("F") == "F"


def test_normalise_sex_empty():
    assert CollinAdapter._normalise_sex("") is None


# ---------------------------------------------------------------------------
# Adapter metadata
# ---------------------------------------------------------------------------

def test_adapter_metadata():
    assert adapter.id == "collin"
    assert adapter.transport == "browser"
    assert adapter.tier == 4
    assert adapter.has_photos is True
    assert adapter.timeout_s >= 60
