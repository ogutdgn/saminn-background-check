"""Collin County, TX — Judicial Online Search (MudBlazor / Blazor Server / SignalR) (Tier 4, browser).

URL: https://apps2.collincountytx.gov/JudicialOnlineSearch2/global

Combined jail + court portal. We scrape the **Inmate** tab (current-custody jail roster) —
same purpose as Tarrant and Hunt. The single search box is a live-filter: typing a name fires
a SignalR message and the Inmate/Case/Warrants tabs update in place without a page reload.
There is no REST/JSON API — all data arrives via the SignalR websocket into the Blazor DOM.

Inmate tab columns: Name (Last, First Middle) · Year of Birth · Sex · Booking Date · SO Number ·
Search Fields (alias highlights). The SO Number drives mugshot fetching via fetch_detail.

Flow:
  1. Navigate to /global — wait for Blazor hydration (window.Blazor defined + search input visible)
  2. Type the search term into the single search box
  3. Wait for the SignalR round-trip to settle (tab count text stabilises)
  4. Walk EVERY page of the Inmate tab (not just page 1), scraping rows from the live DOM
  5. Classify each row by its "Search Fields" column and keep name + alias matches

Incapsula bot-protection: playwright-stealth patches navigator.webdriver + a dozen other
fingerprint fields so the challenge never fires. The BrowserManager handles this for all
browser adapters.

Mugshots: the booking photo lives on the per-inmate detail page (…/inmate/<guid>) as a
data:image the Blazor app injects on load. The detail GUID is only revealed by CLICKING the
row (it is not in the row HTML, and the SO number is not directly navigable), so fetch_detail
re-runs the surname search, clicks the SO's row, and reads the photo on demand.

Data-pull policy (why a row is kept — mirrors the reference scraper):
  The single search box does a GLOBAL match — the Inmate tab returns a row when the query
  hits the person's name, one of their **aliases**, OR the **attorney** on their case.
  The "Search Fields" column tells us which ("Alias: …" / "Attorney: …").
    • NAME   — the person's actual surname matches the query        → keep.
    • ALIAS  — the person uses the query as an AKA (different legal  → keep (a background
               surname, e.g. "Villareal" aka "Smith, Michael")         check must surface it).
    • ATTORNEY / OTHER — the query only matched a lawyer or an       → drop (noise). This is
               unclassifiable field, not the person                     the bulk of a common
                                                                        surname like "Smith".
  Every kept row carries matched_on=[NAME|ALIAS] so the UI can distinguish real-name hits
  from AKA hits. One InmateRecord per roster row.
"""
from __future__ import annotations

import re

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

_HOST = "https://apps2.collincountytx.gov"
_URL = f"{_HOST}/JudicialOnlineSearch2/global"

# Playwright selectors — all CSS, kept as constants so they're easy to update if the
# MudBlazor markup changes. The app is Blazor Server, so selectors target rendered HTML.
_SEL_SEARCH = "input[placeholder='Search']"
_SEL_TAB_INMATE = ".mud-tab"  # first .mud-tab on page = "Inmate (N)" tab button

# --- Pagination selectors ---------------------------------------------------
# Pagination is the historically fragile part (see script-codes SCRAPER_NOTES §Collin).
# Three traps, all handled below:
#   1. The Inmate / Case / Warrants tabs each render their OWN table + pager into the DOM
#      at once (hidden tabs are display:none, not removed). Target the Inmate table by its
#      header columns, NEVER by "first table on page" or nth-index.
#   2. MudTable nests <table> → div.mud-table-container → div.mud-table (outer wrapper).
#      The Next-page button lives in the OUTER mud-table wrapper. A substring match on
#      contains(@class,'mud-table') stops at mud-table-container (no pager), so pagination
#      silently dies after page 1. Match the exact ' mud-table ' class token.
#   3. The pager aria-label varies by MudBlazor version: "Next page" (older) or
#      "Go to next page" (newer). Accept both.
_XP_INMATE_TABLE = (
    "xpath=//table[.//th[normalize-space()='Name'] "
    "and .//th[normalize-space()='Year of Birth'] "
    "and .//th[normalize-space()='Booking Date']]"
)
_XP_MUD_WRAPPER = (  # from a table, walk up to its outer ' mud-table ' wrapper (trap #2)
    "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' mud-table ')][1]"
)
_SEL_NEXT_BTN = "button[aria-label='Next page'], button[aria-label='Go to next page']"  # trap #3
_SEL_PAGE_CAPTION = ".mud-table-page-number-information"  # "1-10 of 54"

# --- Detail (mugshot) selectors ---------------------------------------------
# An inmate row, located by its SO Number cell — used by fetch_detail to click through to
# the detail page (whose GUID URL is only revealed by the click, never present in the row).
_XP_ROW_BY_SO = (
    "xpath=//table[.//th[normalize-space()='Booking Date']]"
    "//tbody//tr[.//td[@data-label='SO Number' and normalize-space()='{so}']]"
)
_URL_INMATE_DETAIL_GLOB = "**/inmate/**"  # detail URL after a row click: …/JudicialOnlineSearch2/inmate/<guid>

# Safety bound: a broad surname whose hits are one attorney's whole caseload can span many
# pages of noise. Stop after this many pages and report `partial` rather than hang.
_MAX_PAGES = 40

# Regex to pull the Inmate count from the tab label "Inmate (54)" → 54
_TAB_COUNT_RE = re.compile(r"Inmate\s*\((\d[\d,]*)\)")

_NAME_RE = re.compile(r"^([^,]+),\s*(.+)$")   # "Last, First Middle" → (last, rest)
# "Search Fields" cell → leading label before the colon: "Alias: …" / "Attorney: …".
_SEARCH_FIELD_RE = re.compile(r"^\s*([A-Za-z][A-Za-z ]*?)\s*:\s*(.*)$", re.S)


class CollinAdapter(Adapter):
    id = "collin"
    display_name = "Collin County"
    transport = "browser"
    tier = 4
    has_photos = True
    portal_url = _URL   # public Judicial Online Search landing/search page (contract: every live source declares one)
    timeout_s = 90.0   # Blazor init (~5 s cold) + SignalR round-trip + DOM settle

    async def search(self, query: SearchQuery, ctx: AdapterContext) -> AdapterResult:
        if ctx.browser is None:
            return self._fail(
                AdapterStatus.ERROR, ctx.now_ms(), "BrowserManager not available — check app startup"
            )
        start = ctx.now_ms()
        try:
            async with ctx.browser.new_page() as page:
                # 1. Navigate and wait for Blazor/SignalR hydration.
                await page.goto(_URL, wait_until="domcontentloaded", timeout=ctx.timeout_s * 1000)
                await page.wait_for_selector(_SEL_SEARCH, timeout=30_000)

                # 2. Capture the pre-filter Inmate count as a baseline. The tab label passes
                #    through transient values on load ("Inmate (0)" → "Inmate (1,373)"), so
                #    this is only a reference point for detecting "the filter has applied".
                initial_count = await self._read_inmate_count(page)

                # 3. Type the search term. MudTextField's debounced binding listens for real
                #    keypress events — page.fill() sets the value but fires only one input
                #    event the binding ignores, so the filter never runs. Clear then
                #    press_sequentially (character-by-character) to drive the binding.
                term = query.last.strip().upper()
                if query.first:
                    term = f"{term}, {query.first.strip().upper()}"
                inp = page.locator(_SEL_SEARCH).first
                await inp.click()
                await inp.fill("")
                await inp.press_sequentially(term, delay=80)
                await inp.press("Tab")

                # 4. Wait for the Inmate count to SETTLE on the filtered value. After typing
                #    "SMITH, JOHN" the tab passes through "Inmate (0)" and the unfiltered
                #    "Inmate (1,373)" before landing on "Inmate (25)". We must wait for a value
                #    that (a) differs from the pre-filter baseline and (b) holds steady — a
                #    naive "first change" read catches a transient and wrongly returns 0.
                inmate_total = await self._wait_for_settled_count(page, initial_count)

                # No settled non-zero count → the search genuinely has no matches.
                if not inmate_total:
                    return self._envelope(AdapterStatus.NO_RESULTS, [], 0, start)

                # 6. Walk EVERY page of the Inmate tab (MudBlazor paginates 10 rows/page),
                #    classifying each row and keeping only name + alias matches. Attorney /
                #    other noise is dropped by the parser, so it never counts toward
                #    max_results — we keep paging until we have enough real matches, the pager
                #    is drained, or we hit the page-count safety bound.
                all_records: list[InmateRecord] = []
                seen: set = set()
                pages_walked = 0
                pager_exhausted = False
                while pages_walked < _MAX_PAGES:
                    pages_walked += 1
                    html = await page.content()
                    for r in self._parse_inmate_rows(html, query):
                        so = r.raw.get("so_number")
                        key = so or (r.name, r.year_of_birth)   # dedup across re-renders
                        if key in seen:
                            continue
                        seen.add(key)
                        all_records.append(r)
                    if len(all_records) >= query.max_results:
                        break
                    if not await self._go_next_page(page):
                        pager_exhausted = True
                        break

            if not all_records:
                return self._envelope(AdapterStatus.NO_RESULTS, [], 0, start)

            # `total` = count of real (name + alias) matches we actually found. We only know
            # it is exhaustive when we drained the pager; if we stopped on max_results or the
            # page bound, more may exist → report `partial` with the count we have as a floor.
            records = all_records[: query.max_results]
            total = len(all_records)
            partial = (not pager_exhausted) or total > len(records)
            return self._envelope(AdapterStatus.OK, records, total, start, partial=partial)

        except Exception as e:
            return self._fail(AdapterStatus.ERROR, start, str(e))

    async def _go_next_page(self, page) -> bool:
        """Advance the Inmate table's pager by one page.

        Returns False when there is no enabled Next button (last page reached, or no pager
        because the result set fits one page). Targets the Inmate table specifically — the
        Case and Warrants tabs render their own pagers into the same DOM — and waits for the
        page caption ("11-20 of 54") to change so the next page.content() reflects the new
        rows rather than the ones we just scraped.
        """
        inmate_tbl = page.locator(_XP_INMATE_TABLE).first
        if await inmate_tbl.count() == 0:
            return False
        wrapper = inmate_tbl.locator(_XP_MUD_WRAPPER).first
        next_btn = wrapper.locator(_SEL_NEXT_BTN).first
        if await next_btn.count() == 0 or await next_btn.is_disabled():
            return False

        caption = wrapper.locator(_SEL_PAGE_CAPTION).first
        before = ((await caption.text_content()) or "").strip() if await caption.count() else ""
        await next_btn.scroll_into_view_if_needed()
        await next_btn.click()
        # Poll for the caption to change (bounded ~5 s), then return so the loop re-scrapes.
        for _ in range(25):
            await page.wait_for_timeout(200)
            now = ((await caption.text_content()) or "").strip() if await caption.count() else ""
            if now and now != before:
                break
        return True

    @staticmethod
    async def _read_inmate_count(page) -> int | None:
        """Current Inmate tab count ("Inmate (25)" → 25), or None if not shown yet."""
        try:
            el = await page.query_selector(_SEL_TAB_INMATE)
            if el is None:
                return None
            m = _TAB_COUNT_RE.search(await el.text_content() or "")
            return int(m.group(1).replace(",", "")) if m else None
        except Exception:
            return None

    async def _wait_for_settled_count(
        self, page, initial: int | None, *,
        poll_ms: int = 120, stable_ms: int = 600, deadline_ms: int = 15_000,
    ) -> int | None:
        """Poll the Inmate count until it settles on the FILTERED value.

        After typing, the count churns (0 → unfiltered roster → filtered result) as SignalR
        updates arrive. We accept a value only once it (a) differs from the pre-filter
        `initial` baseline and (b) has held steady for `stable_ms` — this skips the transient
        load states that a naive first-change read would mistake for the answer. Returns the
        settled count, or the pre-filter `initial` unchanged if nothing new ever settled
        (i.e. a genuine no-result, where the count stays at its baseline).
        """
        needed = max(1, -(-stable_ms // poll_ms))   # ceil(stable_ms / poll_ms)
        steps = max(1, deadline_ms // poll_ms)
        settled_val: int | None = None
        run = 0
        for _ in range(steps):
            cur = await self._read_inmate_count(page)
            if cur is not None and cur != initial:
                if cur == settled_val:
                    run += 1
                    if run >= needed:
                        return cur
                else:
                    settled_val, run = cur, 1
                    if needed == 1:
                        return cur
            await page.wait_for_timeout(poll_ms)
        # Deadline hit: trust the CURRENT on-screen count — by now the DOM has long settled,
        # so this is the real answer (0 for a genuine no-result), not a stale transient.
        cur = await self._read_inmate_count(page)
        if cur is not None:
            return cur
        return settled_val if settled_val is not None else initial

    async def fetch_detail(self, record_id: str, ctx: AdapterContext) -> InmateRecord | None:
        """Fetch one inmate's mugshot + detail deep-link, on demand.

        `record_id` is the packed "SURNAME|SO" from the list record's detail_id. The Collin
        detail page is keyed by an opaque GUID that only exists once you CLICK the row (it is
        never in the row HTML and the SO number is not directly navigable), so we re-run the
        surname search in the browser, paginate to the row with this SO Number, click it, and
        read the booking photo the detail page injects as a data:image. Returns an
        InmateRecord with photo_base64 (raw base64, no data: prefix) and source_url set to the
        per-inmate deep link, or None if unavailable (no browser, row gone, no photo).
        """
        if ctx.browser is None:
            return None
        surname, _, so = record_id.partition("|")
        surname, so = surname.strip().upper(), so.strip()
        if not surname or not so:
            return None
        try:
            async with ctx.browser.new_page() as page:
                await page.goto(_URL, wait_until="domcontentloaded", timeout=ctx.timeout_s * 1000)
                await page.wait_for_selector(_SEL_SEARCH, timeout=30_000)

                initial = await self._read_inmate_count(page)
                inp = page.locator(_SEL_SEARCH).first
                await inp.click()
                await inp.fill("")
                await inp.press_sequentially(surname, delay=80)
                await inp.press("Tab")
                if not await self._wait_for_settled_count(page, initial):
                    return None

                # Paginate to the row carrying this SO Number, then click through to detail.
                row_sel = _XP_ROW_BY_SO.format(so=so)
                clicked = False
                for _ in range(_MAX_PAGES):
                    row = page.locator(row_sel).first
                    if await row.count() > 0:
                        await row.scroll_into_view_if_needed()
                        await row.click()
                        clicked = True
                        break
                    if not await self._go_next_page(page):
                        break
                if not clicked:
                    return None

                await page.wait_for_url(_URL_INMATE_DETAIL_GLOB, timeout=15_000)
                detail_url = page.url
                photo = await self._extract_booking_photo(page)
                if photo is None:
                    # No mugshot (old/released record) — still return the deep link so the UI
                    # can offer a navigable source, matching the always-a-link contract.
                    return InmateRecord(
                        source=self.id, source_url=detail_url, name="",
                        matched_on=[MatchInfo(type=MatchType.NAME)],
                    )
                return InmateRecord(
                    source=self.id, source_url=detail_url, name="",
                    photo_base64=photo, matched_on=[MatchInfo(type=MatchType.NAME)],
                )
        except Exception:
            return None

    @staticmethod
    async def _extract_booking_photo(page) -> str | None:
        """Read the detail page's booking mugshot as raw base64 (data: prefix stripped).

        Blazor injects the photo a beat AFTER the metadata renders, so we wait for any
        data:image to appear (bounded), preferring the one labelled "Booking Photo".
        """
        try:
            await page.wait_for_function(
                """() => {
                    for (const i of document.querySelectorAll('img')) {
                        if ((i.getAttribute('src') || '').startsWith('data:image')) return true;
                    }
                    return false;
                }""",
                timeout=10_000,
            )
        except Exception:
            pass  # no photo appeared in budget — may genuinely have none
        src = await page.evaluate(
            """() => {
                const named = document.querySelector('img[alt="Booking Photo"]');
                if (named && (named.getAttribute('src') || '').startsWith('data:image')) {
                    return named.getAttribute('src');
                }
                for (const i of document.querySelectorAll('img')) {
                    const s = i.getAttribute('src') || '';
                    if (s.startsWith('data:image')) return s;
                }
                return null;
            }"""
        )
        if not src:
            return None
        return src.split(",", 1)[1] if "," in src else src  # frontend re-adds the data: prefix

    # ------------------------------------------------------------------
    # Pure HTML parser — no browser dependency; tested against fixtures
    # ------------------------------------------------------------------

    def _parse_inmate_rows(self, html: str, query: SearchQuery) -> list[InmateRecord]:
        """Parse the rendered Inmate tab table from a page.content() snapshot.

        One InmateRecord per KEPT row. A row is kept when it is a NAME match (the person's
        surname matches the query) or an ALIAS match (the Search Fields column says the
        query is one of their aliases). Attorney/other rows — the bulk of a common-surname
        global search — are dropped as noise. See the module docstring's data-pull policy.
        """
        tree = HTMLParser(html)
        table = self._inmate_table(tree)
        if table is None:
            return []

        surname = query.last.strip().upper()
        out: list[InmateRecord] = []
        for row in table.css("tbody tr"):
            # Use separator=" " so <b>Blake</b>Kevin doesn't collapse to "BlakeKevin" —
            # the Collin site bolds the matched term in each cell, leaving no space in the
            # raw text nodes when the highlighted word is adjacent to the next word.
            cells = [" ".join(td.text(separator=" ", strip=True).split()) for td in row.css("td")]
            if len(cells) < 5:
                continue
            raw_name, yob, sex, booking_date, so_number = cells[0], cells[1], cells[2], cells[3], cells[4]
            search_fields = cells[5] if len(cells) > 5 else ""

            last, first = self._split_name(raw_name)
            if not last:
                continue

            # NAME match: the person's real surname starts with the query surname (prefix
            # match covers "SMITH" → "SMITH, JOHN" and "BLAK" → "BLAKE"), OR the query
            # appears as a word in their first/middle name (e.g. "Holland, Joshua Blake"
            # when searching "BLAKE" — Collin's global search matches full-name tokens,
            # not just the surname, so we must too).
            full_name_tokens = set((last + " " + (first or "")).upper().split())
            if last.upper().startswith(surname) or surname in full_name_tokens:
                matched_on = [MatchInfo(type=MatchType.NAME)]
            else:
                # Not a name match — keep it ONLY if the Search Fields column classifies it
                # as an alias (the person uses the query as an AKA). Attorney/other → drop.
                cls = self._classify_search_fields(search_fields)
                if cls is None or cls[0] is not MatchType.ALIAS:
                    continue
                matched_on = [MatchInfo(type=cls[0], detail=cls[1])]

            name_display = f"{last}, {first}".strip(", ") if first else last

            out.append(
                InmateRecord(
                    source=self.id,
                    source_url=_URL,
                    name=name_display,
                    year_of_birth=yob or None,
                    sex=self._normalise_sex(sex),
                    booking_date=booking_date or None,
                    matched_on=matched_on,
                    charges=[],   # Inmate roster has no charge detail on the list
                    raw={
                        "so_number": so_number or None,
                        # detail_id drives fetch_detail (the on-demand mugshot). The detail
                        # page is keyed by an opaque GUID only revealed by clicking the row —
                        # unreachable from an SO number alone — so fetch_detail must re-run the
                        # surname search and click the SO's row. We pack both it needs here.
                        "detail_id": f"{surname}|{so_number}" if so_number else None,
                        "search_fields": search_fields or None,
                    },
                )
            )
        return out

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_search_fields(search_fields: str) -> tuple[MatchType, str] | None:
        """Classify the 'Search Fields' cell → (MatchType, detail), or None if empty.

        The cell is prefixed with the field that matched: "Alias: SMITH, JOHN…",
        "Attorney: Smith, John H". We read the label before the colon. Anything we don't
        recognise is OTHER (still returned, but the caller drops non-alias matches).
        """
        sf = (search_fields or "").strip()
        if not sf:
            return None
        m = _SEARCH_FIELD_RE.match(sf)
        if not m:
            return (MatchType.OTHER, sf)
        label, rest = m.group(1).strip().lower(), m.group(2).strip()
        if label == "alias":
            return (MatchType.ALIAS, f"Alias: {rest}")
        if label == "attorney":
            return (MatchType.ATTORNEY, f"Attorney: {rest}")
        return (MatchType.OTHER, sf)

    @staticmethod
    def _inmate_table(tree: HTMLParser):
        """Return the Inmate table, identified by its unique header columns.

        The Inmate / Case / Warrants tabs each render a table into the DOM at once, so we
        can't pick by position — the Inmate one is whichever <thead> carries Name +
        Year of Birth + Booking Date. Falls back to the first table on the page (covers the
        single-table fixtures and any markup where the headers aren't found).
        """
        for t in tree.css("table"):
            headers = {th.text(strip=True) for th in t.css("thead th")}
            if {"Name", "Year of Birth", "Booking Date"} <= headers:
                return t
        return tree.css_first("table")

    @staticmethod
    def _split_name(raw: str) -> tuple[str | None, str | None]:
        """'Last, First Middle' → (last, first_middle). Returns (raw, None) if no comma."""
        m = _NAME_RE.match(raw.strip())
        if m:
            return m.group(1).strip(), m.group(2).strip()
        return (raw.strip() or None), None

    @staticmethod
    def _normalise_sex(raw: str) -> str | None:
        v = raw.strip().upper()
        if v in ("M", "MALE"):
            return "M"
        if v in ("F", "FEMALE"):
            return "F"
        return None if not v else v

    def _envelope(self, status, records, total, start_ms, *, partial=False):
        return AdapterResult(
            source=self.id, display_name=self.display_name, status=status,
            records=records, total=total, partial=partial,
            duration_ms=self.now_ms() - start_ms,
        )

    def _fail(self, status, start_ms, error=None):
        return AdapterResult(
            source=self.id, display_name=self.display_name, status=status,
            duration_ms=self.now_ms() - start_ms, error=error,
        )

    @staticmethod
    def now_ms() -> int:
        import time
        return int(time.monotonic() * 1000)
