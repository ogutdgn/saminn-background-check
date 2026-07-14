"""Denton County, TX — Tyler "Public Access DC" District Court Criminal Records (Tier 3, http).

Same self-hosted Tyler instance as DentonAdapter (justice1.dentoncounty.gov) but a separate
ASP.NET application: /PublicAccessDC/. This module covers **District Court** (felonies) while
the existing DentonAdapter covers JP & County Criminal (misdemeanors). Both are Tier 3 —
identical VIEWSTATE/EVENTVALIDATION replay flow, identical magic fields.

Flow (District Clerk Criminal Case Records, `Search.aspx?ID=100`):
  GET  /PublicAccessDC/default.aspx          -> session cookie
  POST /PublicAccessDC/Search.aspx?ID=100    -> node-aware search form (fresh __VIEWSTATE)
       with NodeID = "All District Courts" comma-list
  POST /PublicAccessDC/Search.aspx?ID=100    -> CaseSearchResults.aspx

Key differences from /PublicAccess/:
  - Host sub-path is /PublicAccessDC/ (separate ASP.NET app, own session)
  - Search ID=100 = "District Clerk Criminal Case Records" (ID=200 = civil/family — wrong door)
  - NodeID values differ (district court numbers vs JP court numbers)
  - BaseConnKy=DF still works for defendant-only results

Results carry: Case Number · (Citation empty for felonies) · Defendant Info (name + DOB) ·
Filed/Location/Judge · Type/Status (Felony by Indictment / Felony by Information / etc.) ·
Charge(s). Identical column layout to /PublicAccess/ — same parsers work unchanged.
No mugshots. DOB normalized to year only.
"""
from __future__ import annotations

import re
from contextlib import asynccontextmanager

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

_HOST = "https://justice1.dentoncounty.gov/PublicAccessDC"
_SEARCH = f"{_HOST}/Search.aspx?ID=100"   # District Clerk Criminal Case Records
_ALL_DC = (
    "1251,1252,1253,1254,1255,1256,1260,1265,1270,1280,"
    "72004,72005,72006,72007,72008"
)
_ALL_DC_DESC = "------ All District Courts ------"

_DOB_RE = re.compile(r"(\d{2}/\d{2}/(\d{4}))\s*$")
_FILED_RE = re.compile(r"^(\d{1,2}/\d{1,2}/\d{4})\s+(.*)$")
_COUNT_RE = re.compile(r"Record Count:.*?<b>\s*([\d,]+)\s*</b>", re.DOTALL)
_CASEID_RE = re.compile(r"CaseID=(\d+)")


class DentonDCAdapter(Adapter):
    id = "denton_dc"
    display_name = "Denton County (District Court)"
    transport = "http"
    tier = 3
    has_photos = False
    timeout_s = 45.0
    RESULT_CAP = 400

    async def search(self, query: SearchQuery, ctx: AdapterContext) -> AdapterResult:
        start = ctx.now_ms()
        try:
            # Use an isolated client so our ASP.NET_SessionId cookie doesn't collide with
            # DentonAdapter's session on the same domain (justice1.dentoncounty.gov).
            async with self._isolated_client(ctx) as http:
                return await self._do_search(http, query, ctx, start)
        except httpx.TimeoutException as e:
            return self._fail(AdapterStatus.TIMEOUT, start, str(e))
        except Exception as e:
            return self._fail(AdapterStatus.ERROR, start, str(e))

    async def _do_search(self, http, query, ctx, start) -> AdapterResult:
        try:
            await http.get(f"{_HOST}/default.aspx", timeout=ctx.timeout_s)
            nf = await http.post(
                _SEARCH,
                data={"NodeID": _ALL_DC, "NodeDesc": _ALL_DC_DESC},
                headers={"Referer": f"{_HOST}/default.aspx"},
                timeout=ctx.timeout_s,
            )
            nf.raise_for_status()
            resp = await http.post(
                _SEARCH, data=self._search_form(nf.text, query),
                headers={"Referer": _SEARCH}, timeout=ctx.timeout_s,
            )
            resp.raise_for_status()
            html = resp.text
            if "Exception" in html and "Render" in html:
                raise ValueError("Denton DC results render error (a magic field is wrong)")

            total = self._record_count(html)
            records = self._parse_results(html)
            if not records:
                if total == 0 or "No cases matched" in html:
                    return self._envelope(AdapterStatus.NO_RESULTS, [], 0, start)
                raise ValueError("results page had no parseable rows and no 0-records marker")
            partial = len(records) >= self.RESULT_CAP
            return self._envelope(AdapterStatus.OK, records, total, start, partial=partial)
        except httpx.TimeoutException:
            raise
        except Exception:
            raise

    async def fetch_detail(self, record_id: str, ctx: AdapterContext) -> InmateRecord | None:
        try:
            if not record_id.isdigit():
                return None
            async with self._isolated_client(ctx) as http:
                await http.get(f"{_HOST}/default.aspx", timeout=ctx.timeout_s)
                resp = await http.get(
                    f"{_HOST}/CaseDetail.aspx", params={"CaseID": record_id},
                    headers={"Referer": _SEARCH}, timeout=ctx.timeout_s,
                )
            resp.raise_for_status()
            d = self._parse_detail(resp.text)
            if not d["sheet"]:
                return None
            return InmateRecord(
                source=self.id,
                source_url=f"{_HOST}/CaseDetail.aspx?CaseID={record_id}",
                name="",
                matched_on=[MatchInfo(type=MatchType.NAME)],
                charges=d["charges"],
                raw={"case_id": record_id, "case_no": d["case_no"], "detail_text": d["sheet"]},
            )
        except Exception:
            return None

    @staticmethod
    def _search_form(node_form_html: str, query: SearchQuery) -> dict:
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
            "NameTypeKy": "ALIAS", "BaseConnKy": "DF",
            "LastName": (query.last or "").strip(),
            "FirstName": (query.first or "").strip(),
            "MiddleName": (query.middle or "").strip(),
            "AllStatusTypes": "true", "StatusType": "true", "ShowInactive": "false",
            "RequireFirstName": "False", "ExactName": "false",
            "SortBy": "casenumber", "SearchSubmit": "Search",
            "NodeID": _ALL_DC,
        })
        return data

    def _parse_results(self, html: str) -> list[InmateRecord]:
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
            case_id_m = _CASEID_RE.search(link.attributes.get("href") or "")
            case_id = case_id_m.group(1) if case_id_m else None

            out.append(
                InmateRecord(
                    source=self.id,
                    source_url=f"{_HOST}/CaseDetail.aspx?CaseID={case_id}" if case_id else None,
                    name=name,
                    year_of_birth=year,
                    sex=None,
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
                        "detail_id": case_id,
                        "case_no": case_no or None,
                        "citation": citation or None,
                        "court": court,
                        "filed": filed,
                    },
                )
            )
        return out

    def _parse_detail(self, html: str) -> dict:
        tree = HTMLParser(html)
        out: dict = {"case_no": None, "charges": [], "sheet": ""}
        container = tree.css_first(".ssCaseDetailBody") or tree.body
        if container is None:
            return out
        text = container.text(separator="\n")
        lines = [ln.replace("\xa0", " ").rstrip() for ln in text.split("\n") if ln.strip()]
        out["sheet"] = "\n".join(lines)
        m = re.search(r"Case No\.\s*([A-Za-z0-9\-]+)", out["sheet"])
        out["case_no"] = m.group(1) if m else None
        for row in tree.css("table tr"):
            tds = [c.text(strip=True) for c in row.css("td")]
            if len(tds) >= 2 and tds[0] and re.match(r"^\d+\.?$", tds[0]) and len(tds[1]) > 3:
                out["charges"].append(Charge(offense=tds[1], extra={"detail": " ".join(tds[2:]) or None}))
        return out

    @staticmethod
    def _results_table(tree: HTMLParser):
        for t in tree.css("table"):
            if t.css_first("a[href*=CaseDetail]") is not None:
                return t
        return None

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

    @asynccontextmanager
    async def _isolated_client(self, ctx: AdapterContext):
        """Fresh AsyncClient with its own cookie jar and transport.

        In tests we share the MockTransport so test fixtures still intercept requests.
        In production we create a completely independent client — sharing the real
        transport would cause its aclose() to shut down ctx.http's connection pool,
        breaking every other adapter that runs after us on the same context.
        """
        transport = getattr(ctx.http, "_transport", None)
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        if isinstance(transport, httpx.MockTransport):
            async with httpx.AsyncClient(
                transport=transport, headers=headers, follow_redirects=True, timeout=ctx.timeout_s
            ) as client:
                yield client
        else:
            async with httpx.AsyncClient(
                headers=headers, follow_redirects=True, timeout=ctx.timeout_s
            ) as client:
                yield client

    def _envelope(self, status, records, total, start_ms, *, partial=False):
        return AdapterResult(
            source=self.id, display_name=self.display_name, status=status,
            records=records, total=total, partial=partial,
            duration_ms=AdapterContext.now_ms() - start_ms,
        )

    def _fail(self, status, start_ms, error=None):
        return AdapterResult(
            source=self.id, display_name=self.display_name, status=status,
            duration_ms=AdapterContext.now_ms() - start_ms, error=error,
        )
