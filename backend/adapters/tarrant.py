"""Tarrant County — Sheriff inmate roster (Tier 1, http).

JSON jTable API at inmatesearch.tarrantcounty.com. Current-custody only; has mugshots.
Request flow + gotchas: backend/tests/fixtures/tarrant/README.md.

  search()   -> list-level records (name, year, sex) — the fast, rate-respectful pull.
  hydrate()  -> fills charges + mugshot for ONE record (an extra 2 calls per person).
               Kept lazy on purpose: a common surname is dozens of rows, and eagerly
               fetching detail for all of them would hammer the site (N+1).

Accuracy notes: `year_of_birth` is the 4-digit year off the full DOB (unambiguous);
the full DOB and every raw field are preserved in `raw`. Tarrant searches the roster
name directly, so every row is a real-name match (`matched_on = NAME`).
"""
from __future__ import annotations

import json
import re

import httpx

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
    Sex,
)

_BASE = "https://inmatesearch.tarrantcounty.com"
_MUGSHOT_RE = re.compile(r"data:image/[a-zA-Z]+;base64,([A-Za-z0-9+/=]+)")


class TarrantAdapter(Adapter):
    id = "tarrant"
    display_name = "Tarrant County"
    transport = "http"
    tier = 1

    LIST_URL = f"{_BASE}/Home/GetSearchResults"
    DETAIL_URL = f"{_BASE}/Home/Details"
    BOOKINGS_URL = f"{_BASE}/Home/GetActiveBookings"

    # -- live search -------------------------------------------------------

    async def search(self, query: SearchQuery, ctx: AdapterContext) -> AdapterResult:
        start = ctx.now_ms()
        try:
            # raceId=All / sexId=Both are REQUIRED — blank silently returns zero rows.
            form = {
                "lastName": query.last.upper(),
                "firstName": (query.first or "").upper(),
                "cid": "",
                "raceId": "All",
                "sexId": self._sex_param(query.sex),
                "recordsId": "50",
                "jtStartIndex": "0",
                "jtPageSize": str(min(query.max_results, 50)),
                "jtSorting": "FirstMiddleName ASC",
            }
            resp = await ctx.http.post(
                self.LIST_URL,
                data=form,
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=ctx.timeout_s,
            )
            resp.raise_for_status()
            records = self._parse_list(resp.content)
            total = json.loads(resp.content).get("TotalRecordCount")
            status = AdapterStatus.OK if records else AdapterStatus.NO_RESULTS
            return AdapterResult(
                source=self.id,
                display_name=self.display_name,
                status=status,
                records=records,
                total=total,
                duration_ms=ctx.now_ms() - start,
            )
        except httpx.TimeoutException as e:
            return self._fail(AdapterStatus.TIMEOUT, start, str(e))
        except Exception as e:  # never raise out of search()
            return self._fail(AdapterStatus.ERROR, start, str(e))

    async def hydrate(self, record: InmateRecord, ctx: AdapterContext) -> None:
        """Fill `charges` + `photo_base64` for one record (2 extra calls). Lazy by design."""
        cid = record.raw.get("CID")
        if not cid:
            return
        bookings = await ctx.http.post(
            self.BOOKINGS_URL,
            data={"cid": cid, "jtStartIndex": "0", "jtPageSize": "100", "jtSorting": "ArrestDate ASC"},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=ctx.timeout_s,
        )
        record.charges = self._parse_bookings(bookings.content)
        if record.charges:
            record.booking_date = record.charges[0].extra.get("BookInDate")
        detail = await ctx.http.get(self.DETAIL_URL, params={"CID": cid}, timeout=ctx.timeout_s)
        record.photo_base64 = self._extract_mugshot(detail.content)

    # -- pure parsers (fixture-tested) ------------------------------------

    def _parse_list(self, content: bytes | str) -> list[InmateRecord]:
        data = json.loads(content)
        out: list[InmateRecord] = []
        for rec in data.get("Records", []):
            last = (rec.get("LastName") or "").strip()
            first_middle = (rec.get("FirstMiddleName") or "").strip()
            name = f"{last}, {first_middle}" if first_middle else last
            cid = rec.get("CID")
            out.append(
                InmateRecord(
                    source=self.id,
                    source_url=f"{self.DETAIL_URL}?CID={cid}" if cid else None,
                    name=name,
                    year_of_birth=self._derive_year(rec.get("DOB")),
                    sex=self._norm_sex(rec.get("Sex")),
                    matched_on=[MatchInfo(type=MatchType.NAME)],
                    raw=dict(rec),  # keep the source row verbatim
                )
            )
        return out

    def _parse_bookings(self, content: bytes | str) -> list[Charge]:
        data = json.loads(content)
        mapped = {"Charge", "CaseNumber", "WarrantNumber"}
        charges: list[Charge] = []
        for rec in data.get("Records", []):
            charges.append(
                Charge(
                    offense=rec.get("Charge"),
                    case_no=rec.get("CaseNumber"),
                    warrant_no=rec.get("WarrantNumber"),
                    disposition=None,  # jail roster: no court outcome
                    extra={k: v for k, v in rec.items() if k not in mapped},
                )
            )
        return charges

    def _extract_mugshot(self, html: bytes | str) -> str | None:
        text = html.decode("utf-8", "replace") if isinstance(html, bytes) else html
        m = _MUGSHOT_RE.search(text)
        return m.group(1) if m else None

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _sex_param(sex: Sex | None) -> str:
        if sex is Sex.MALE:
            return "M"
        if sex is Sex.FEMALE:
            return "F"
        return "Both"

    @staticmethod
    def _derive_year(dob: str | None) -> str | None:
        if not dob:
            return None
        year = str(dob).split("/")[-1].strip()
        return year if len(year) == 4 and year.isdigit() else None

    @staticmethod
    def _norm_sex(sex: str | None) -> str | None:
        # Unrecognized -> None (never fabricate "U"); the raw value is kept in raw["Sex"].
        if not sex:
            return None
        return {"male": "M", "female": "F", "m": "M", "f": "F"}.get(sex.strip().lower())

    def _fail(self, status: AdapterStatus, start_ms: int, error: str | None = None) -> AdapterResult:
        return AdapterResult(
            source=self.id,
            display_name=self.display_name,
            status=status,
            duration_ms=AdapterContext.now_ms() - start_ms,
            error=error,
        )
