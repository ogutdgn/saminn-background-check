"""Oklahoma (statewide) — ODCR "On Demand Court Records" (Tier 2, http).

One adapter for **all of Oklahoma**: ODCR (odcr.com) is a statewide court-case index
covering 70+ District Courts + several Tribal Courts. HTML, server-rendered. Court
records → **dispositions are baked into the offense text**, and there are **NO mugshots,
NO DOB, NO sex/race anywhere** (a pure case index — name-only identity). Spike notes +
fixtures + field map: backend/tests/fixtures/odcr/README.md.

Flow (POST-redirect-GET, session cookie):
  GET /                         -> session cookie + search form
  POST /search (party=...)      -> 302, auto-followed (client follow_redirects=True)
       └─ redirect lands on     -> GET /results  == page 1
  GET /results?page=N           -> further pages (~15 rows/page)
The server **caps at 1,000 results** (paginates to ~page 67). Like Dallas, we page with
a dedup set + a time budget and mark the result `partial` when we stop before the end.

Accuracy notes: ODCR carries no biographical identity data, so `year_of_birth`, `sex`,
and `photo_base64` stay None and matches are **name-only** (a human confirms identity
from case context). We search `party-type=P+D` (Plaintiffs & Defendants — the parties,
never attorneys), the analog of Dallas's `nameType=DF`, so rows are real-name matches →
`matched_on = NAME` with the party role in `.detail`. **One InmateRecord per result row**
(one case); no person-grouping — ODCR has no identity key to group on. The "Offense or
Cause" cell blends offense + disposition with a " - ST " delimiter; we split it for parity
with Dallas but keep the full original text in `Charge.extra` so nothing is lost.
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import parse_qs, urlparse

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

_HOST = "https://odcr.com"
_SEARCH = f"{_HOST}/search"
_RESULTS = f"{_HOST}/results"
_OFFENSE_DISP_SEP = " - ST "   # "<offense> - ST <disposition>" in the Offense-or-Cause cell


class OdcrAdapter(Adapter):
    id = "odcr"
    display_name = "Oklahoma (ODCR)"
    transport = "http"
    tier = 2
    timeout_s = 45.0   # POST /search is cold-slow (~16s) on the first hit of a session; give margin

    max_pages = 20         # safety cap on the paging loop (server caps results at 1,000 / ~67 pages)
    page_delay_s = 0.15    # politeness pause between pages (ODCR is open, but be a good citizen)
    budget_margin_s = 3.0  # stop paging this long before the orchestrator's hard timeout

    async def search(self, query: SearchQuery, ctx: AdapterContext) -> AdapterResult:
        start = ctx.now_ms()
        try:
            # 1. GET / to obtain the session cookie the search is keyed to.
            await ctx.http.get(f"{_HOST}/", timeout=ctx.timeout_s)
            # 2. POST the search; the 302 to /results is auto-followed -> page 1 HTML.
            resp = await ctx.http.post(_SEARCH, data=self._form(query), timeout=ctx.timeout_s)
            resp.raise_for_status()
            html = resp.text

            total = self._result_count(html)
            rows = self._parse_rows(html)
            if not rows:
                if self._is_no_results(html, total):
                    return self._envelope(AdapterStatus.NO_RESULTS, [], total, start)
                # had a results page but parsed nothing and it's not a clean "0 results" -> fail loud
                raise ValueError("results page had no parseable rows and no 0-results marker")

            # 3. Page through /results?page=N, accumulating with a dedup set. Stop on the true
            #    end (a page adds nothing new), at max_results / max_pages / the time budget, or
            #    once we've consumed the server-reported total. Stopping early -> `partial`.
            deadline = start + int(max(0.0, ctx.timeout_s - self.budget_margin_s) * 1000)
            records: list[InmateRecord] = []
            seen: set[tuple] = set()
            partial = False
            for page in range(1, self.max_pages + 1):
                added = 0
                for rec in self._parse_rows(html):
                    key = self._row_key(rec)
                    if key in seen:
                        continue
                    seen.add(key)
                    rec.raw["page"] = page
                    records.append(rec)
                    added += 1
                if added == 0:
                    break  # nothing new -> reached the end (or a repeated page)
                if len(records) >= query.max_results:
                    partial = True  # capped at max_results — more may exist
                    break
                if total is not None and len(records) >= total:
                    break  # consumed everything the server reported (complete)
                if AdapterContext.now_ms() >= deadline:
                    partial = True  # out of time budget — more pages exist
                    break
                if page == self.max_pages:
                    partial = True  # hit the page cap — more pages exist
                    break
                if self.page_delay_s:
                    await asyncio.sleep(self.page_delay_s)
                nxt = await ctx.http.get(f"{_RESULTS}?page={page + 1}", timeout=ctx.timeout_s)
                nxt.raise_for_status()
                html = nxt.text
                if "results-list" not in html:
                    break  # defensive: no result table -> end

            return self._envelope(AdapterStatus.OK, records, total, start, partial=partial)
        except httpx.TimeoutException as e:
            return self._fail(AdapterStatus.TIMEOUT, start, str(e))
        except Exception as e:  # never raise out of search()
            return self._fail(AdapterStatus.ERROR, start, str(e))

    # -- request building --------------------------------------------------

    @staticmethod
    def _form(query: SearchQuery) -> dict:
        """ODCR's `party` is "LAST, FIRST". party-type=P+D = the parties (not attorneys),
        court="" = statewide (we rank client-side). Other filters left blank = "any"."""
        party = query.last.strip().upper()
        if query.first:
            party = f"{party}, {query.first.strip().upper()}"
        return {
            "court-group": "",
            "court": "",
            "party": party,
            "party-type": "P+D",
            "case-type": "",
            "case-number-type": "",
            "case-number-year": "",
            "case-number-number": "",
            "filed-start": "",
            "filed-end": "",
            "activity": "",
        }

    # -- pure parsers (fixture-tested) ------------------------------------

    def _parse_rows(self, html: str) -> list[InmateRecord]:
        # One InmateRecord PER result row (one case) — deliberately no person grouping.
        # ODCR has no DOB/sex/identity key, so any grouping would be pure guesswork.
        table = HTMLParser(html).css_first("#results-list")
        if table is None:
            return []
        out: list[InmateRecord] = []
        for row in table.css("tbody tr"):
            num_cell = row.css_first("td.case-number")
            link = num_cell.css_first("a") if num_cell else None
            if link is None:
                continue  # header / spacer / template row — only real rows have a detail link
            href = link.attributes.get("href") or ""
            court_code, casekey = self._parse_detail_link(href)

            name, role = self._parse_party(row.css_first("td.party"))
            if not name:
                continue
            case_no = link.text(strip=True) or None
            court_name = self._cell_text(row, "td.court")
            filed = self._cell_text(row, "td.filed")
            case_style = self._cell_text(row, "td.case")
            offense_raw = self._cell_text(row, "td.offense")
            offense, disposition = self._split_offense(offense_raw)

            out.append(
                InmateRecord(
                    source=self.id,
                    source_url=f"{_HOST}{href}" if href else None,
                    name=name,
                    matched_on=[MatchInfo(type=MatchType.NAME, detail=role)],
                    charges=[
                        Charge(
                            offense=offense,
                            case_no=case_no,
                            disposition=disposition,
                            extra={
                                "court": court_name,
                                "filed": filed,
                                "offense_or_cause": offense_raw,  # full text, never lost
                            },
                        )
                    ],
                    raw={
                        "court_name": court_name,
                        "court_code": court_code,
                        "casekey": casekey,
                        "case_style": case_style,
                        "filed": filed,
                        "party_role": role,
                    },
                )
            )
        return out

    @staticmethod
    def _result_count(html: str) -> int | None:
        """The server-reported count from `<p id="duration">…N results…</p>`
        ("Limited to 1,000 results" when capped, "0 results" when none)."""
        node = HTMLParser(html).css_first("#duration")
        if node is None:
            return None
        m = re.search(r"([\d,]+)\s+results?", node.text())
        return int(m.group(1).replace(",", "")) if m else None

    @staticmethod
    def _is_no_results(html: str, total: int | None) -> bool:
        if total == 0:
            return True
        # belt-and-suspenders: an empty results table with no detail links
        table = HTMLParser(html).css_first("#results-list")
        if table is None:
            return False
        return table.css_first("td.case-number a") is None

    @staticmethod
    def _split_offense(text: str | None) -> tuple[str | None, str | None]:
        """"<offense> - ST <disposition>" -> (offense, disposition). No delimiter -> all
        offense, no disposition. The full original is preserved by the caller in extra."""
        text = (text or "").strip()
        if not text:
            return None, None
        if _OFFENSE_DISP_SEP in text:
            offense, disposition = text.rsplit(_OFFENSE_DISP_SEP, 1)
            return offense.strip() or None, disposition.strip() or None
        return text, None

    @staticmethod
    def _parse_party(cell) -> tuple[str | None, str | None]:
        """The party cell is "<name> <span class='type'>Role</span>". Pull the role from
        the span, then the name is what remains (whitespace collapsed)."""
        if cell is None:
            return None, None
        role_node = cell.css_first("span.type")
        role = role_node.text(strip=True) if role_node else None
        if role_node is not None:
            role_node.decompose()  # remove the role so only the name text is left
        name = " ".join(cell.text().split())
        return (name or None), role

    @staticmethod
    def _parse_detail_link(href: str) -> tuple[str | None, str | None]:
        """/detail?court=003-&casekey=003-CM++0500249 -> ("003-", "003-CM  0500249").
        parse_qs decodes the '+'-encoded spaces in the casekey."""
        q = parse_qs(urlparse(href).query)
        court_code = (q.get("court") or [None])[0]
        casekey = (q.get("casekey") or [None])[0]
        return court_code, casekey

    @staticmethod
    def _cell_text(row, selector: str) -> str | None:
        node = row.css_first(selector)
        if node is None:
            return None
        return node.text(strip=True) or None

    @staticmethod
    def _row_key(rec: InmateRecord) -> tuple:
        """Stable identity of one result row, for dedup across pages: the court + casekey
        (a unique case id), falling back to displayed case number + name."""
        c = rec.charges[0] if rec.charges else None
        return (
            rec.raw.get("court_code"),
            rec.raw.get("casekey"),
            c.case_no if c else None,
            rec.name,
        )

    # -- envelope helpers --------------------------------------------------

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
