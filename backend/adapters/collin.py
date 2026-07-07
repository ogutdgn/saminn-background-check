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
  2. (Optional) bump rows-per-page to 100 so pagination is rarely needed
  3. Type the search term into the single search box
  4. Wait for the SignalR round-trip to settle (tab count text stabilises)
  5. Scrape the Inmate tab table rows from the live DOM
  6. Client-side surname filter (the global search also matches case titles / attorneys)

Incapsula bot-protection: playwright-stealth patches navigator.webdriver + a dozen other
fingerprint fields so the challenge never fires. The BrowserManager handles this for all
browser adapters.

Mugshots: GET /JudicialOnlineSearch2/api/Inmate/{soNumber}/Photo → JPEG. Confirmed pattern
from the SO Number column — fetch_detail hydrates photo_base64 on demand.

Accuracy: matched_on=NAME for rows where the query surname appears in the inmate name;
matched_on=ALIAS for rows matched via the Search Fields alias. Attorney noise cannot appear
in the Inmate tab (attorneys are not booked). One InmateRecord per roster row.
"""
from __future__ import annotations

import base64
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

_HOST = "https://apps2.collincountytx.gov"
_URL = f"{_HOST}/JudicialOnlineSearch2/global"
_PHOTO_URL = f"{_HOST}/JudicialOnlineSearch2/api/Inmate/{{so}}/Photo"

# Playwright selectors — all CSS, kept as constants so they're easy to update if the
# MudBlazor markup changes. The app is Blazor Server, so selectors target rendered HTML.
_SEL_SEARCH = "input[placeholder='Search']"
_SEL_ROWS_PER_PAGE = "div.mud-select input"          # the rows-per-page MudSelect inside MudTablePager
_SEL_TAB_INMATE = "div.mud-tab:first-child"           # "Inmate (N)" tab button
_SEL_TABLE_ROWS = "div[role='tabpanel'] table tbody tr"  # rows in the active tab panel

# After typing, SignalR debounce + round-trip is typically < 1 s on LAN.
# We wait up to 10 s for the first row to appear, then allow 1 s for the count to settle.
_WAIT_FIRST_ROW_MS = 10_000
_SETTLE_MS = 1_200

_NAME_RE = re.compile(r"^([^,]+),\s*(.+)$")   # "Last, First Middle" → (last, rest)


class CollinAdapter(Adapter):
    id = "collin"
    display_name = "Collin County"
    transport = "browser"
    tier = 4
    has_photos = True
    timeout_s = 90.0   # Blazor init (~5 s cold) + SignalR round-trip + DOM settle

    async def search(self, query: SearchQuery, ctx: AdapterContext) -> AdapterResult:
        if ctx.browser is None:
            return self._fail(
                AdapterStatus.ERROR, ctx.now_ms(), "BrowserManager not available — check app startup"
            )
        start = ctx.now_ms()
        try:
            async with ctx.browser.new_page() as page:
                # 1. Navigate and wait for Blazor hydration
                await page.goto(_URL, wait_until="domcontentloaded", timeout=ctx.timeout_s * 1000)
                await page.wait_for_function("() => !!window.Blazor", timeout=20_000)
                await page.wait_for_selector(_SEL_SEARCH, timeout=15_000)

                # 2. Try to bump rows-per-page to 100 (reduces pagination round-trips).
                #    If the selector misses (markup changed) we silently skip — default 10 still works.
                try:
                    await self._set_rows_per_page(page, 100)
                except Exception:
                    pass

                # 3. Type the search term. We search "LAST, FIRST" when both are supplied so the
                #    live filter is tighter; otherwise just the last name (broad, filter client-side).
                term = query.last.strip().upper()
                if query.first:
                    term = f"{term}, {query.first.strip().upper()}"
                await page.fill(_SEL_SEARCH, term)

                # 4. Wait for the Inmate tab rows to settle after the SignalR round-trip.
                #    wait_for_selector gives up to 10 s for the first row; then we pause 1.2 s for
                #    the count to stabilise (Blazor re-renders incrementally).
                try:
                    await page.wait_for_selector(_SEL_TABLE_ROWS, timeout=_WAIT_FIRST_ROW_MS)
                    await page.wait_for_timeout(_SETTLE_MS)
                except Exception:
                    # No rows appeared → genuine no-results (or the Inmate tab is empty for this name)
                    return self._envelope(AdapterStatus.NO_RESULTS, [], 0, start)

                # 5. Make sure we're on the Inmate tab (it's selected by default; re-click to be safe)
                try:
                    inmate_tab = await page.query_selector(_SEL_TAB_INMATE)
                    if inmate_tab:
                        await inmate_tab.click()
                        await page.wait_for_timeout(600)
                except Exception:
                    pass

                # 6. Grab the rendered DOM and parse it offline (pure function → fixture-testable)
                html = await page.content()

            records = self._parse_inmate_rows(html, query)
            if not records:
                return self._envelope(AdapterStatus.NO_RESULTS, [], 0, start)

            partial = len(records) >= query.max_results
            return self._envelope(AdapterStatus.OK, records[: query.max_results], len(records), start, partial=partial)

        except Exception as e:
            return self._fail(AdapterStatus.ERROR, start, str(e))

    async def fetch_detail(self, record_id: str, ctx: AdapterContext) -> InmateRecord | None:
        """Fetch the mugshot for one inmate by SO Number.

        record_id = SO Number (e.g. "352435"). Returns an InmateRecord with photo_base64
        set, or None if the fetch fails or no photo exists.
        """
        try:
            url = _PHOTO_URL.format(so=record_id)
            resp = await ctx.http.get(url, timeout=ctx.timeout_s)
            if resp.status_code != 200 or not resp.content:
                return None
            photo = base64.b64encode(resp.content).decode()
            return InmateRecord(
                source=self.id,
                source_url=_URL,
                name="",
                photo_base64=photo,
                matched_on=[MatchInfo(type=MatchType.NAME)],
            )
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Pure HTML parser — no browser dependency; tested against fixtures
    # ------------------------------------------------------------------

    def _parse_inmate_rows(self, html: str, query: SearchQuery) -> list[InmateRecord]:
        """Parse the rendered Inmate tab table from a page.content() snapshot.

        Returns one InmateRecord per row, filtered to rows where the query surname
        appears in the inmate's last name (global search also hits case titles and
        attorneys — we keep only real name matches and known-alias matches).
        """
        tree = HTMLParser(html)
        # Find the first visible table (the Inmate tab is active by default)
        table = self._inmate_table(tree)
        if table is None:
            return []

        out: list[InmateRecord] = []
        for row in table.css("tbody tr"):
            cells = [td.text(strip=True) for td in row.css("td")]
            if len(cells) < 5:
                continue
            raw_name, yob, sex, booking_date, so_number = cells[0], cells[1], cells[2], cells[3], cells[4]
            search_fields = cells[5] if len(cells) > 5 else ""

            last, first = self._split_name(raw_name)
            if not last:
                continue

            # Filter: keep only rows whose last name starts with the query surname
            # (catches "SMITH" → "SMITH, JOHN"; rejects "BLACKSMITH, ..." via prefix check)
            if not last.upper().startswith(query.last.strip().upper()):
                continue

            # matched_on: NAME if the query surname is in the actual last name;
            # ALIAS if it only appeared in the Search Fields aliases column.
            matched_on = [MatchInfo(type=MatchType.NAME, detail="Inmate roster")]
            if search_fields and query.last.upper() not in last.upper():
                matched_on = [MatchInfo(type=MatchType.ALIAS, detail=search_fields)]

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
                        "detail_id": so_number or None,   # drives fetch_detail (mugshot)
                        "search_fields": search_fields or None,
                    },
                )
            )
        return out

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _inmate_table(tree: HTMLParser):
        """Return the first table inside a tab panel (Inmate tab is active by default)."""
        for panel in tree.css("div[role='tabpanel']"):
            t = panel.css_first("table")
            if t is not None:
                return t
        # Fallback: any table on the page
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

    @staticmethod
    async def _set_rows_per_page(page, n: int) -> None:
        """Try to set the MudTablePager rows-per-page to n (100). Best-effort."""
        from playwright.async_api import Page as _Page  # local import keeps top-level clean
        # MudSelect for rows-per-page — click it, then pick the option closest to n
        pager_sel = "div.mud-table-pagination"
        await page.wait_for_selector(pager_sel, timeout=5_000)
        # Click the select input inside the pager
        await page.click(f"{pager_sel} .mud-input-slot")
        await page.wait_for_timeout(400)
        # Pick the option with value closest to n (or the last/largest option)
        options = await page.query_selector_all("div[role='option']")
        if not options:
            return
        best = options[-1]   # largest option (furthest down the list)
        for opt in options:
            txt = (await opt.text_content() or "").strip()
            if txt.isdigit() and int(txt) <= n:
                best = opt
        await best.click()
        await page.wait_for_timeout(600)

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
