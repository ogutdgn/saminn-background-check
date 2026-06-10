# Tech Stack — decisions & rationale

This records *what* we chose and *why*, so the choices don't get re-litigated every
time someone new opens the repo. If you want to change one of these, that's a
lead-level discussion, not a unilateral swap.

## Locked decisions

| Decision | Choice | Why |
| --- | --- | --- |
| **Where it runs** | On-premise always-on server on the shelter's network | Only a real machine can run a browser (needed for some sources). An office IP looks human to bot-protection, unlike a cloud datacenter IP. PII stays in the building. Central audit. |
| **Backend language** | Python 3.12+ | This is a scraping tool first. Python's scraping/automation ecosystem is best-in-class, and more of the team can work anywhere in it. |
| **Web framework** | FastAPI | `async`-native (essential for parallel fan-out + streaming), Pydantic models double as our data contract, clean Server-Sent Events, auto OpenAPI for the frontend types. |
| **HTTP scraping** | httpx (async) | Concurrent requests for the HTTP-tier sources; async fits the orchestrator. |
| **HTML parsing** | selectolax (fast) or BeautifulSoup (familiar) | Parsing result grids. selectolax is faster; BeautifulSoup is fine if the team knows it better. Pick per adapter; both are acceptable. |
| **Browser scraping** | Playwright (Python) | The only way to read browser-only sources (e.g. Blazor/SignalR sites). First-class Python support. |
| **Concurrency** | asyncio | HTTP adapters run concurrently; browser adapters gated by a semaphore/queue. |
| **Storage** | SQLite | Cache + audit in one file, no DB server, safe for concurrent staff. |
| **Data contract** | Pydantic models | Validated `InmateRecord` / `AdapterResult`; also the API schema; mirrored to TS on the frontend. |
| **Frontend** | React (Vite + TypeScript) + a component library | Flexible, polished look for the intake UI. Talks to the backend over SSE. |
| **Prod serving** | Frontend built to static files, served by FastAPI (or nginx) on the box | One URL, one deployed thing on the server, even though dev runs two servers. |
| **Process mgmt** | systemd service or Docker on the box | Always-on, auto-restart on crash. |

## Decisions intentionally deferred

These do **not** block development. Settle them as the relevant phase arrives:

- **Auth on the internal tool** — do staff log in (named audit entries) or is it an
  open page on a trusted LAN? Decide **before go-live**, because it shapes the audit
  log. Not needed to start building adapters.
- **Browser pool size / rate limits** — tune empirically once the browser manager
  exists and we see real timing.
- **Cache TTL** — a config value; pick a sane default (e.g. a few hours) and adjust.
- **HTML parser choice** — selectolax vs BeautifulSoup, per adapter; not a global lock.
- **Component library** — shadcn/ui vs MUI vs other; the frontend owner picks early.
- **Export format** — PDF vs CSV vs printable HTML for the intake file.
- **Fannin County approach** — browser-render vs reconstructing its JSON call (it
  has a *client-side* CAPTCHA, so it's defeatable within the rules; see SOURCES.md).

## Things we explicitly rejected, and why

- **Serverless / Vercel-style cloud** — cannot run a persistent browser, so the
  browser-only sources die; and it puts PII on rented infrastructure. Rejected.
- **A single all-TypeScript stack** — viable, but Python is the better fit for a
  scraping-heavy tool and a team that mostly knows Python. The polished UI need is
  satisfied by pairing Python with a React frontend instead.
- **CAPTCHA-solving services / stealth WAF evasion** — out of bounds on
  ethics/legal grounds for a shelter handling this data. See the responsible-use
  rules in `ARCHITECTURE.md`. We find another public door instead.
