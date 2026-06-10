# Sources — the map

The list of target sources, how each one gives up its data, and its current build
status. This is living knowledge: every recon (Stage 0 of the add-a-source
pipeline) updates this file.

## The tier system

A source's **tier** is the single most useful fact about it — it predicts the
effort, who should build it, and whether it can run without a browser. Tier is
about *the easiest open door we found*, not about the county.

| Tier | What it means | Effort | Example |
| --- | --- | --- | --- |
| **1** | Real JSON API. Hit endpoint, get structured data. | Lowest | Tarrant (Sheriff jTable JSON) |
| **2** | Stateless HTML. Form POST → HTML you parse. No JS, no tokens. | Low | Dallas, Hunt, ODCR |
| **3** | Stateful HTML. Must replay server tokens (`__VIEWSTATE`, NodeID) or hit magic fields. | Medium | Denton (Tyler Public Access) |
| **4** | Browser-only. No data without a rendered browser (SPA / WebSocket). | High | Collin (Blazor/SignalR) |
| **5** | **Blocked.** Server-side CAPTCHA / WAF with no open alternative door. **Out of scope** per the responsible-use rules. | — | Tyler `*.tylertech.cloud` court portals; OSCN |

> **Key lesson from recon:** "blocked" almost always means *one door* is blocked,
> not that the data is unreachable. A county's court portal can be WAF-walled while
> its Sheriff roster or a statewide system is wide open. Stage 0 recon is about
> finding *all* the doors before declaring a tier.

## Source status

Legend: 🟢 proven reachable · 🟡 reachable, needs effort / unproven end-to-end ·
🔴 blocked (out of scope) · build status: `todo` / `in-progress` / `done`

| Source | Open door (what we'd actually use) | Tier | Transport | Bot protection | Photos | Status | Build |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Tarrant County, TX** | Sheriff inmate roster JSON API (`inmatesearch.tarrantcounty.com`) | 1 | http | none | ✅ mugshots | 🟢 proven | todo |
| **Dallas County, TX** | Criminal Background Search (HTML form POSTs) | 2 | http | none | — | 🟢 proven | todo |
| **Hunt County, TX** | Sheriff jail booking (`apps.huntcounty.net/jail/`, Classic ASP) | 2 | http | none | TBD | 🟢 proven (live roster pulled) | todo |
| **Oklahoma (statewide)** | ODCR (`odcr.com`) — covers 70+ OK counties, HTML POST | 2 | http | reCAPTCHA v3 (invisible, non-blocking) | — | 🟢 proven (1000 results) | todo |
| **Denton County, TX** | Tyler Public Access, *self-hosted* (`justice1.dentoncounty.gov`) | 3 | http | Cloudflare (datacenter IPs may be challenged) | — | 🟢 proven | todo |
| **Collin County, TX** | Judicial Online Search (MudBlazor / SignalR) | 4 | browser | Incapsula (passes with stealth, today) | ✅ mugshots | 🟢 proven | todo |
| **Fannin County, TX** | Vendor jail site (`offenderindex.com/fannincoga`) | 3–4 | http or browser | **client-side** CAPTCHA (defeatable within rules) | TBD | 🟡 reachable, unproven | todo |

### Notes per source

- **Tarrant** — Use the **Sheriff** roster (open JSON), *not* the county's Tyler
  court portal (that one is Tier-5 WAF-blocked). Current-custody only.
- **Hunt** — The county's `*.tylertech.cloud` *court* portal is Tier-5 blocked, but
  the Sheriff's `apps.huntcounty.net/jail/` booking system is wide open Classic ASP
  (`results.asp`). Same pattern as Tarrant.
- **Oklahoma / ODCR** — OSCN (the state docket site) is Tier-5 Cloudflare-Turnstile
  blocked. **ODCR is the parallel system and it's open.** It covers most OK counties
  in one adapter, which makes it high-value. Best practice is to search both OSCN
  and ODCR; we use the open one.
- **Denton** — The only *self-hosted* Tyler instance we use. Self-hosted Tyler works;
  the AWS-hosted `*.tylertech.cloud` ones are all Tier-5. Sensitive to IP reputation
  (on-prem office IP helps).
- **Collin** — Genuinely browser-only (Blazor Server over SignalR; no REST/JSON
  exists — confirmed historically by a 411 on the negotiate endpoint). This is the
  one source that forces the on-prem-with-browser decision.
- **Fannin** — Its CAPTCHA is **client-side JavaScript**, not a server wall, so it's
  within scope to pull (unlike the WAF'd portals). Data loads from a backend
  `/api/data`-style endpoint. Approach undecided: reconstruct the JSON call (Tier 3)
  or render with the browser manager (Tier 4). Stretch goal — build the six proven
  sources first.

## Known Tier-5 (out of scope) — do not re-attempt without a *new public door*

- **Tyler `*.tylertech.cloud` court portals** (Hunt, Fannin, Tarrant court, etc.) —
  AWS WAF "Human Verification" CAPTCHA; some also Google reCAPTCHA. We use these
  counties' *Sheriff/alternate* systems instead.
- **Oklahoma OSCN** (`oscn.net`) — Cloudflare Turnstile on every docket endpoint.
  We use ODCR instead.

If you think you've found a *new, public, non-circumventing* door into one of these,
that's a Stage 0 recon — document it here and review with the lead.

## To investigate (candidate sources)

Anyone running recon on a new county adds a row here first, then fills it in:

| Candidate county / source | Why considered | Recon owner | Status |
| --- | --- | --- | --- |
| _(add candidates here as the source list grows beyond the initial 7)_ | | | |

When recon classifies a candidate, move it into the **Source status** table with
its tier and evidence.
