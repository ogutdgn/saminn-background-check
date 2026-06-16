"""Denton County, TX — Tyler "Public Access" (self-hosted Odyssey) (Tier 3, http).

Self-hosted Tyler Public Access at justice1.dentoncounty.gov. ASP.NET WebForms — **stateful
Tier 3**: we replay `__VIEWSTATE`/`__EVENTVALIDATION` and set the JS-populated "magic fields".
Court records → charges + dispositions + a register-of-actions detail; **no mugshots**, but the
list DOES carry a birth date (we normalize DOWN to year). Spike notes + the cracked field map:
backend/tests/fixtures/denton/README.md.

Flow (JP & County Criminal name search, `Search.aspx?ID=100`):
  GET  /default.aspx                         -> session cookie
  POST /Search.aspx?ID=100 (NodeID, NodeDesc) -> the node-aware search form (fresh __VIEWSTATE)
  POST /Search.aspx?ID=100 (search params)    -> CaseSearchResults.aspx (the result rows)

The load-bearing "magic fields" (from the form's ValidateSearchParameters JS): for a party-name
search it's SearchBy=1, SearchType=PARTY, SearchMode=NAME, NameTypeKy=ALIAS, and — the one that
makes it return defendants — **BaseConnKy=DF**. Plus the boolean hidden fields must be real
"true"/"false" (empty -> Boolean.Parse error) and SortBy must be a valid value. NodeID is the
"All JP & County Courts" comma-list (empty NodeID -> the server bounces to the portal).

Accuracy: court records -> `matched_on = NAME` (defendant search). `year_of_birth` is the year of
the list DOB (we never store the full birthdate of a possible-wrong-person match). No sex on the
list. One InmateRecord per case-row (no grouping). Tyler caps the result list at ~400 (we mark
`partial` when capped).
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

_HOST = "https://justice1.dentoncounty.gov/PublicAccess"
_SEARCH = f"{_HOST}/Search.aspx?ID=100"   # JP & County Court: Criminal Case Records
# The "All JP & County Courts" node (the value of the portal's node selector).
_ALL_COURTS = "1,1101,1110,1102,1003,1104,1105,1106,1107,1108,1270,1280,1310,1320,1330,1340,1350,1360"
_DOB_RE = re.compile(r"(\d{2}/\d{2}/(\d{4}))\s*$")          # trailing DOB in the "Defendant Info" cell
_FILED_RE = re.compile(r"^(\d{1,2}/\d{1,2}/\d{4})\s+(.*)$")  # leading filed date in the location cell
_COUNT_RE = re.compile(r"Record Count:.*?<b>\s*([\d,]+)\s*</b>", re.DOTALL)
_CASEID_RE = re.compile(r"CaseID=(\d+)")


class DentonAdapter(Adapter):
    id = "denton"
    display_name = "Denton County"
    transport = "http"
    tier = 3
    has_photos = False
    timeout_s = 45.0   # Tier-3 multi-step (GET + 2 POSTs) through Cloudflare; give margin
    RESULT_CAP = 400   # Tyler Public Access caps the result list

    async def search(self, query: SearchQuery, ctx: AdapterContext) -> AdapterResult:
        start = ctx.now_ms()
        try:
            # 1. session
            await ctx.http.get(f"{_HOST}/default.aspx", timeout=ctx.timeout_s)
            # 2. establish the court node -> the node-aware search form (with fresh __VIEWSTATE)
            nf = await ctx.http.post(
                _SEARCH,
                data={"NodeID": _ALL_COURTS, "NodeDesc": "All JP & County Courts"},
                timeout=ctx.timeout_s,
            )
            nf.raise_for_status()
            # 3. the actual party-name (defendant) search
            resp = await ctx.http.post(
                _SEARCH, data=self._search_form(nf.text, query),
                headers={"Referer": _SEARCH}, timeout=ctx.timeout_s,
            )
            resp.raise_for_status()
            html = resp.text
            if "Exception" in html and "Render" in html:
                raise ValueError("Denton results render error (a magic field is wrong)")

            total = self._record_count(html)
            records = self._parse_results(html)
            if not records:
                if total == 0 or "No cases matched" in html:
                    return self._envelope(AdapterStatus.NO_RESULTS, [], 0, start)
                raise ValueError("results page had no parseable rows and no 0-records marker")
            # partial if Tyler capped the list (400) OR the page rendered fewer rows than its own
            # reported Record Count (defensive — a truncated render should never read as complete).
            partial = len(records) >= self.RESULT_CAP or (total is not None and len(records) < total)
            return self._envelope(AdapterStatus.OK, records, total, start, partial=partial)
        except httpx.TimeoutException as e:
            return self._fail(AdapterStatus.TIMEOUT, start, str(e))
        except Exception as e:  # never raise out of search()
            return self._fail(AdapterStatus.ERROR, start, str(e))

    async def fetch_detail(self, record_id: str, ctx: AdapterContext) -> InmateRecord | None:
        """Pull one case's full record (CaseDetail.aspx = Register of Actions): all charges +
        a readable case sheet (Party / Charge / Events / Financial). `record_id` is
        "<CaseID>|<last>|<first>" (first may be empty).

        CaseDetail.aspx is SESSION-RELATIVE — it only loads after the session has run a search whose
        result set CONTAINS this case (a cold GET, or a search that doesn't surface it, returns a
        Public Access Error). So we re-run the defendant's own last+first search — which always
        surfaces their own case, where a surname-only search can push older cases past Tyler's 400
        cap — THEN GET CaseDetail. Never raises -> None."""
        try:
            parts = record_id.split("|")
            case_id = parts[0]
            last = parts[1].strip() if len(parts) > 1 else ""
            first = parts[2].strip() if len(parts) > 2 else ""
            if not case_id.isdigit() or not last:
                return None
            # seed the session with the same narrow search that surfaced this case (results discarded)
            await ctx.http.get(f"{_HOST}/default.aspx", timeout=ctx.timeout_s)
            nf = await ctx.http.post(
                _SEARCH, data={"NodeID": _ALL_COURTS, "NodeDesc": "All JP & County Courts"},
                timeout=ctx.timeout_s,
            )
            nf.raise_for_status()
            await ctx.http.post(
                _SEARCH, data=self._search_form(nf.text, SearchQuery(last=last, first=first or None)),
                headers={"Referer": _SEARCH}, timeout=ctx.timeout_s,
            )
            resp = await ctx.http.get(
                f"{_HOST}/CaseDetail.aspx", params={"CaseID": case_id},
                headers={"Referer": _SEARCH}, timeout=ctx.timeout_s,
            )
            resp.raise_for_status()
            d = self._parse_detail(resp.text)
            if not d["sheet"]:
                return None
            return InmateRecord(
                source=self.id,
                source_url=None,   # CaseDetail is session-relative — no shareable external URL
                name="",           # the list record already carries the matched name; merged in the UI
                matched_on=[MatchInfo(type=MatchType.NAME)],
                charges=d["charges"],
                raw={"case_id": case_id, "case_no": d["case_no"], "detail_text": d["sheet"]},
            )
        except Exception:
            return None

    # -- request building --------------------------------------------------

    @staticmethod
    def _search_form(node_form_html: str, query: SearchQuery) -> dict:
        """Take all inputs from the node-aware form (incl. __VIEWSTATE + the populated NodeID),
        then set the party-name (defendant) search fields — BaseConnKy=DF is the load-bearing one."""
        form = HTMLParser(node_form_html).css_first("#SearchParameters") or HTMLParser(node_form_html).css_first("form")
        data: dict = {}
        if form is not None:
            for inp in form.css("input"):
                n = inp.attributes.get("name")
                if not n:
                    continue
                if inp.attributes.get("type") in ("radio", "checkbox") and inp.attributes.get("checked") is None:
                    continue
                data[n] = inp.attributes.get("value") or ""
        data.update({
            "SearchBy": "1", "PartySearchMode": "Name",
            "SearchType": "PARTY", "SearchMode": "NAME",
            "NameTypeKy": "ALIAS", "BaseConnKy": "DF",   # DF = Defendant (the fix)
            "LastName": (query.last or "").strip(),
            "FirstName": (query.first or "").strip(),
            "MiddleName": (query.middle or "").strip(),
            "AllStatusTypes": "true", "StatusType": "true", "ShowInactive": "false",
            "RequireFirstName": "False", "ExactName": "false",
            "SortBy": "casenumber", "SearchSubmit": "Search",
        })
        return data

    # -- pure parsers (fixture-tested) ------------------------------------

    def _parse_results(self, html: str) -> list[InmateRecord]:
        """One InmateRecord per result row (a case). Columns: Case Number, Citation, Defendant
        Info (name + DOB), Filed/Location/Judge, Type/Status (disposition), Charge(s)."""
        table = self._results_table(HTMLParser(html))
        if table is None:
            return []
        out: list[InmateRecord] = []
        for row in table.css("tr"):
            link = row.css_first("a[href*=CaseDetail]")
            if link is None:
                continue
            tds = [c.text(separator=" ", strip=True) for c in row.css("td")]
            if len(tds) < 6:
                continue
            case_no, citation, name_dob, filed_loc, status, charge = tds[0], tds[1], tds[2], tds[3], tds[4], tds[5]
            name, year = self._split_name_dob(name_dob)
            if not name:
                continue
            filed, court = self._split_filed_loc(filed_loc)
            m = _CASEID_RE.search(link.attributes.get("href") or "")
            case_id = m.group(1) if m else None
            # detail_id packs the CaseID AND the defendant's own last|first — fetch_detail must re-run a
            # search to seed the session before CaseDetail.aspx (session-relative) will load, and Tyler
            # only loads a case that's in the session's CURRENT result set. Surname-only would re-seed a
            # broader set whose 400-cap can push older cases out (then CaseDetail errors); re-seeding with
            # the defendant's own last+first always surfaces their own case. No external source_url: the
            # CaseDetail URL only works inside a searched session, so a shareable link would 404.
            last, first = self._split_last_first(name)
            detail_id = f"{case_id}|{last}|{first}" if case_id and last else None

            out.append(
                InmateRecord(
                    source=self.id,
                    source_url=None,
                    name=name,
                    year_of_birth=year,           # year of the list DOB (full birthdate not retained)
                    sex=None,                     # not on the Denton list
                    matched_on=[MatchInfo(type=MatchType.NAME, detail="Defendant")],
                    charges=[
                        Charge(
                            offense=charge or None,
                            case_no=case_no or None,
                            disposition=status or None,
                            extra={"citation": citation or None, "court": court, "filed": filed},
                        )
                    ],
                    raw={
                        "case_id": case_id,
                        "detail_id": detail_id,    # "<CaseID>|<surname>" -> fetch_detail / UI case sheet
                        "case_no": case_no or None,
                        "citation": citation or None,
                        "court": court,
                        "filed": filed,
                    },
                )
            )
        return out

    _DETAIL_SECTIONS = (
        "Party Information", "Charge Information", "Events & Orders of the Court", "Financial Information",
    )

    def _parse_detail(self, html: str) -> dict:
        """The CaseDetail "Register of Actions" -> a readable case sheet + the charge list. The page
        has no single content container; each section is a <table> headed by .ssCaseDetailSectionTitle."""
        tree = HTMLParser(html)
        out: dict = {"case_no": None, "charges": [], "sheet": ""}
        body = tree.body
        if body is None:
            return out
        m = re.search(r"Case No\.?\s*\n?\s*([A-Za-z0-9\-]+)", body.text(separator="\n"))
        out["case_no"] = m.group(1) if m else None

        lines: list[str] = []
        for tbl in tree.css("table"):
            head = tbl.css_first(".ssCaseDetailSectionTitle")
            if head is None:
                continue
            title = head.text(strip=True)
            if title not in self._DETAIL_SECTIONS:
                continue
            rows = [re.sub(r"\s+", " ", ln).strip()
                    for ln in tbl.text(separator="\n").split("\n") if ln.strip()]
            rows = [ln for ln in rows if ln != title]
            lines.append(title.upper())
            lines += ["  " + ln for ln in rows[:30]]   # cap each section (the docket can be long)
            lines.append("")
            if title == "Charge Information":
                for row in tbl.css("tr"):
                    cells = [c.text(strip=True) for c in row.css("td")]
                    if len(cells) >= 2 and re.match(r"^\d+\.$", cells[0]) and len(cells[1]) > 3:
                        out["charges"].append(Charge(
                            offense=cells[1],
                            extra={"statute": cells[2] if len(cells) > 2 else None,
                                   "level": cells[3] if len(cells) > 3 else None},
                        ))
        out["sheet"] = "\n".join(lines).strip()
        return out

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _results_table(tree: HTMLParser):
        for t in tree.css("table"):
            if t.css_first("a[href*=CaseDetail]") is not None:
                return t
        return None

    @staticmethod
    def _split_last_first(name: str) -> tuple[str, str]:
        """"Last, First Middle" -> ("Last", "First"). First is the first token after the comma (Tyler's
        name search is a prefix match, so the first given name is enough to surface the defendant's own
        case). Returns ("", "") components empty when absent."""
        last, _, rest = (name or "").partition(",")
        first = rest.strip().split(" ", 1)[0] if rest.strip() else ""
        return last.strip(), first

    @staticmethod
    def _split_name_dob(cell: str) -> tuple[str | None, str | None]:
        cell = (cell or "").strip()
        m = _DOB_RE.search(cell)
        if m:
            return (cell[: m.start()].strip() or None), m.group(2)
        return (cell or None), None

    @staticmethod
    def _split_filed_loc(cell: str) -> tuple[str | None, str | None]:
        cell = (cell or "").strip()
        m = _FILED_RE.match(cell)
        if m:
            return m.group(1), (m.group(2).strip() or None)
        return None, (cell or None)

    @staticmethod
    def _record_count(html: str) -> int | None:
        m = _COUNT_RE.search(html)
        return int(m.group(1).replace(",", "")) if m else None

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
