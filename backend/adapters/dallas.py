"""Dallas County — Criminal Background Search (Tier 2, http).

Court case info (felony + misdemeanor) at dallascounty.org/criminalBackgroundSearch.
HTML, not JSON. Court records → has dispositions, has NO mugshots. Session flow +
gotchas: backend/tests/fixtures/dallas/README.md.

Flow: GET / (sets JSESSIONID, serves a disclaimer gate misleadingly named "captcha"
but NOT a CAPTCHA) → POST /captcha (Continue) → POST /searchByName. Results are one
row per charge/case; we group rows into one record per person (keyed on name + DOB
token), each carrying its charges.

Accuracy notes: `year_of_birth` is left None — Dallas DOB is a 2-digit-year MMDDYY,
often masked (000000), so the century is ambiguous; we don't guess. The raw token is
kept in `raw["dob"]`. We search as Defendant (nameType=DF) → `matched_on = NAME`. The
`ARC` flag is preserved in `Charge.extra` but not interpreted as alias without proof.
"""
from __future__ import annotations

import asyncio

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
    Sex,
)

_BASE = "https://www.dallascounty.org/criminalBackgroundSearch"
_NO_RESULTS_MARKER = "No records were found"


class DallasAdapter(Adapter):
    id = "dallas"
    display_name = "Dallas County"
    transport = "http"
    tier = 2

    max_pages = 15        # safety cap on the paging loop
    page_delay_s = 0.05   # small politeness pause (Dallas has only a disclaimer gate, no WAF)
    budget_margin_s = 3.0  # stop paging this long before the orchestrator's hard timeout

    async def search(self, query: SearchQuery, ctx: AdapterContext) -> AdapterResult:
        start = ctx.now_ms()
        try:
            # 1. disclaimer gate — GET sets the session, POST "Continue" accepts it.
            await ctx.http.get(f"{_BASE}/", timeout=ctx.timeout_s)
            await ctx.http.post(f"{_BASE}/captcha", data={"submit": "Continue"}, timeout=ctx.timeout_s)
            # 2. the actual name search (as Defendant; blank race/sex = "any").
            form = {
                "lastName": query.last.upper(),
                "firstName": (query.first or "").upper(),
                "middleName": (query.middle or "").upper(),
                "nameType": "DF",
                "race": " ",
                "sex": self._sex_param(query.sex),
                "dobMonth": "", "dobDay": "", "dobYear": "",
                "numberType": "", "pending": "",
                "searchbyname": "Search By Name",
            }
            resp = await ctx.http.post(f"{_BASE}/searchByName", data=form, timeout=ctx.timeout_s)
            resp.raise_for_status()
            html = resp.text

            if self._is_no_results(html):
                return self._envelope(AdapterStatus.NO_RESULTS, [], 0, start)

            # Follow pagination: POST /paging (which=down) carrying the session cookie.
            # Each page re-numbers rows 01.. and returns a fresh set, so we accumulate with a
            # dedup set. We stop when a page adds NO new rows (true end), or — when more results
            # still exist — at max_results / the page cap / a TIME BUDGET. A common name like
            # "John Smith" has hundreds of court records; without the budget, paging the whole
            # session blows past the orchestrator's hard timeout and loses everything. When we
            # stop early we mark the result `partial` so the UI can say "refine your search".
            deadline = start + int(max(0.0, ctx.timeout_s - self.budget_margin_s) * 1000)
            records: list[InmateRecord] = []
            seen: set[tuple] = set()
            partial = False
            for page in range(1, self.max_pages + 1):
                added = 0
                for rec in self._parse_results(html):
                    rec.raw["page"] = page  # detail_ln is page- and session-relative
                    key = self._row_key(rec)
                    if key in seen:
                        continue
                    seen.add(key)
                    records.append(rec)
                    added += 1
                if added == 0:
                    break  # nothing new on this page -> we've reached the true end (complete)
                if self._distinct_names(records) >= query.max_results:
                    partial = True  # capped at max_results — more may exist
                    break
                if AdapterContext.now_ms() >= deadline:
                    partial = True  # out of time budget — more pages exist
                    break
                if page == self.max_pages:
                    partial = True  # hit the page cap — more pages exist
                    break
                if self.page_delay_s:
                    await asyncio.sleep(self.page_delay_s)
                nxt = await ctx.http.post(f"{_BASE}/paging", data={"which": "down"}, timeout=ctx.timeout_s)
                nxt.raise_for_status()
                html = nxt.text
                if "defendant_detail" not in html:
                    break  # next page has no result links -> reached the end (complete)

            if not records:
                # had a result table but parsed nothing -> fail loud
                raise ValueError("results page had no parseable rows and no no-records marker")
            # total stays None (Dallas reports no count); `partial` signals if we capped.
            return self._envelope(AdapterStatus.OK, records, None, start, partial=partial)
        except httpx.TimeoutException as e:
            return self._fail(AdapterStatus.TIMEOUT, start, str(e))
        except Exception as e:  # never raise out of search()
            return self._fail(AdapterStatus.ERROR, start, str(e))

    # -- pure parsers (fixture-tested) ------------------------------------

    def _parse_results(self, html: str) -> list[InmateRecord]:
        # One record PER case-row — deliberately NO person-level grouping here.
        # Dallas's list has no reliable person key: the DOB is frequently masked
        # ("000000"), so grouping on (name, DOB) both wrongly SPLITS one person across
        # masked/unmasked rows and wrongly MERGES two distinct same-name people who
        # both have a masked DOB (dropping one's sex, misattributing charges). Either
        # is "silently wrong". Person-level dedup is deferred to the client-side
        # ranking layer, which can weigh confidence and a human confirms identity.
        table = HTMLParser(html).css_first("table.table-striped")
        if table is None:
            return []
        # columns: [ln#, LN(name), ARC, RS, DOB, CASE/BOND, CT, CHARGE, DISP]
        out: list[InmateRecord] = []
        for row in table.css("tr"):
            cells = row.css("td")
            if len(cells) < 9:
                continue  # header / spacer
            v = [c.text(strip=True) for c in cells]
            _ln, name_raw, arc, rs, dob, case_bond, ct, charge_txt, disp = v[:9]
            name = " ".join(name_raw.split())
            if not name:
                continue
            link = row.css_first("a[href*=defendant_detail]")
            out.append(
                InmateRecord(
                    source=self.id,
                    name=name,
                    year_of_birth=None,  # masked/2-digit DOB -> don't guess a year
                    sex=self._parse_sex(rs),
                    matched_on=[MatchInfo(type=MatchType.NAME)],
                    charges=[
                        Charge(
                            offense=charge_txt or None,
                            case_no=case_bond or None,
                            disposition=disp or None,
                            extra={"court": ct or None, "arc": arc or None},
                        )
                    ],
                    raw={
                        "rs": rs or None,
                        "dob": dob or None,
                        "detail_ln": link.attributes.get("href") if link else None,
                        "row": v,
                    },
                )
            )
        return out

    @staticmethod
    def _is_no_results(html: str) -> bool:
        return _NO_RESULTS_MARKER in html

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _sex_param(sex: Sex | None) -> str:
        if sex is Sex.MALE:
            return "M"
        if sex is Sex.FEMALE:
            return "F"
        return " "  # blank = any

    @staticmethod
    def _parse_sex(rs: str | None) -> str | None:
        # RS is race+sex, e.g. "WM" (White Male), "UU" (Unknown). Sex is the 2nd char.
        if not rs or len(rs) < 2:
            return None
        return {"M": "M", "F": "F"}.get(rs[1].upper(), "U")

    @staticmethod
    def _row_key(rec: InmateRecord) -> tuple:
        """Identity of one case-row, for dedup across pages."""
        c = rec.charges[0] if rec.charges else None
        return (
            rec.name,
            rec.raw.get("dob"),
            c.case_no if c else None,
            c.offense if c else None,
            c.disposition if c else None,
        )

    @staticmethod
    def _distinct_names(records: list[InmateRecord]) -> int:
        return len({r.name for r in records})

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
