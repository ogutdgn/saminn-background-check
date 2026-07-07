# Collin County — Stage 1 spike notes & fixture guide

**Source:** https://apps2.collincountytx.gov/JudicialOnlineSearch2/global  
**Tier:** 4 (browser — Blazor Server / MudBlazor / SignalR)  
**Recon date:** 2026-07-06  

---

## What the site does

Combined jail + court portal. Single search box on the `/global` page. Results split into
three tabs that update live via SignalR as you type:

| Tab | Contents | Our use |
|---|---|---|
| **Inmate** | Current-custody jail roster | ✅ primary target |
| **Case** | Court case index (1.6 M records) | stretch — future |
| **Warrants** | Active warrants | stretch — future |

### Inmate tab columns
`Name` (Last, First Middle) · `Year of Birth` · `Sex` · `Booking Date` · `SO Number` · `Search Fields` (alias highlights)

### Key gotchas
- **No REST API.** All data arrives via SignalR websocket into the Blazor DOM. Playwright is the only option.
- **Global search, not surname-only.** Typing "SMITH" matches any field containing that string — case titles, attorney names, etc. The adapter filters client-side to keep only rows where the inmate last name starts with the query surname.
- **Rows per page default = 10.** The adapter tries to bump this to 100 via the MudTablePager dropdown before searching.
- **Incapsula bot-protection.** Passes with playwright-stealth patches. The `BrowserManager` in `core/browser.py` applies `stealth_async()` to every new page.
- **Mugshots.** SO Number → `GET /JudicialOnlineSearch2/api/Inmate/{so}/Photo` → JPEG. Loaded on-demand via `fetch_detail`.
- **SignalR debounce.** After filling the search input, the adapter waits up to 10 s for the first row then 1.2 s to settle. On a LAN connection the round-trip is ~200–800 ms.

---

## How to capture fixtures (Stage 1)

Run this spike script from the project root (venv active, playwright installed):

```python
# spike_collin.py — run once to capture fixtures; not part of the app
import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

URL = "https://apps2.collincountytx.gov/JudicialOnlineSearch2/global"

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False,  # visible so you can watch
            args=["--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ))
        page = await ctx.new_page()
        await stealth_async(page)
        await page.goto(URL, wait_until="domcontentloaded")
        await page.wait_for_function("() => !!window.Blazor")
        await page.wait_for_selector("input[placeholder='Search']")

        # Capture 1: search returning results (use a common surname)
        await page.fill("input[placeholder='Search']", "SMITH")
        await page.wait_for_timeout(3000)
        with open("backend/tests/fixtures/collin/results_smith.html", "w", encoding="utf-8") as f:
            f.write(await page.content())
        print("Saved results_smith.html")

        # Capture 2: search returning no results
        await page.fill("input[placeholder='Search']", "ZZZNOTAREALNAME")
        await page.wait_for_timeout(3000)
        with open("backend/tests/fixtures/collin/results_empty.html", "w", encoding="utf-8") as f:
            f.write(await page.content())
        print("Saved results_empty.html")

        await browser.close()

asyncio.run(main())
```

Run: `python spike_collin.py`

The two HTML files go here (`backend/tests/fixtures/collin/`) and are git-ignored (they
contain real booking data). Once captured, update `test_collin.py` to use them.

---

## Field map

| DOM cell | InmateRecord field | Notes |
|---|---|---|
| Name (col 0) | `name` | "Last, First Middle" — kept as-is |
| Year of Birth (col 1) | `year_of_birth` | 4-digit year string |
| Sex (col 2) | `sex` | "Male"→"M", "Female"→"F" |
| Booking Date (col 3) | `booking_date` | "M/D/YYYY" string |
| SO Number (col 4) | `raw.so_number` + `raw.detail_id` | Key for fetch_detail mugshot |
| Search Fields (col 5) | `raw.search_fields` | Alias text; drives ALIAS matched_on |
