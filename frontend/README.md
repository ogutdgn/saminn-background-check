# frontend/

The React (Vite + TypeScript) UI for intake staff. It is **deliberately dumb**: it
renders whatever the backend streams and contains no scraping logic and no
per-county special-casing beyond display.

## Responsibilities

- A search box (one name in).
- A **result card per source** that updates live as SSE events arrive: pending →
  ok / no-results / error, with counts.
- Render each `InmateRecord`: name, year of birth, sex, charges, mugshot (when
  present), and **why it matched** (`matched_on`) — defaulting to real-name matches
  and letting staff reveal alias/attorney noise.
- Let staff **mark records relevant** and **export a report** for the intake file.

## Conventions

- React + TypeScript. Talks to the backend over **SSE** (`POST /api/search`,
  `text/event-stream`).
- Types for `InmateRecord` / `AdapterResult` are **generated from the backend's
  OpenAPI schema**, not hand-written — so the contract can't drift.
- A component library (shadcn/ui, MUI, or similar) is chosen by the frontend owner
  early. Keep the look clean and legible; this is a tool used under time pressure at
  intake, not a marketing page.
- No business logic about *how* sources are scraped ever lives here.

## Set up in Phase 1 (not yet present)

- The Vite app scaffold, the component library, and the dev proxy to the backend's
  `/api` are created in the first frontend phase. This folder is docs-only for now.

## Prod

Built to static files and served by the backend (or nginx) on the on-prem box, so
staff use a single internal URL.
