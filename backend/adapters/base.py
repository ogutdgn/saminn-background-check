"""The shared contract — the keystone of the system.

Every adapter, the orchestrator, the API, and (via generated types) the frontend
depend on the shapes defined here. A change ripples to everyone, so this file
changes rarely and deliberately. Full rationale in docs/ARCHITECTURE.md.

Three parts:
  • OUTPUT  — what every adapter returns: `InmateRecord` (one person, normalized)
              wrapped in an `AdapterResult` (one source's outcome).
  • INPUT   — `SearchQuery`: the normalized search fanned out to every source.
  • CONTRACT — the `Adapter` ABC every source implements, and the per-search
              `AdapterContext` handed to it.

Design notes baked in from real recon (Tarrant JSON + Dallas HTML, 2026-06-12):
  • Only `name` (output) and `last` (input) are required. Everything else is
    optional because sources populate wildly different subsets — a jail roster has
    a mugshot but no disposition; a court search has dispositions but no photo.
  • `raw` / `Charge.extra` are escape hatches: anything a source provides that
    doesn't map to a common field is kept verbatim there, so the common shape can
    stay small without losing data.
  • `year_of_birth` is a *string* on output (preserve whatever the source gives,
    incl. nothing) but an *int* on input (a clean value we control). We normalize
    DOWN to year — never store full birthdates of possible-wrong-person matches.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from enum import Enum

import httpx
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# OUTPUT — the normalized record every adapter must produce
# ---------------------------------------------------------------------------


class MatchType(str, Enum):
    """WHY a row matched the query — lets the UI surface real-name hits and hide
    attorney/alias noise. Tagging this correctly per source is the adapter's job."""

    NAME = "name"          # the query is in the person's real name
    ALIAS = "alias"        # matched a known alias / AKA
    ATTORNEY = "attorney"  # matched the attorney, not the defendant
    OTHER = "other"


class MatchInfo(BaseModel):
    type: MatchType
    detail: str | None = None   # e.g. "Alias: SMITH, JOHN"


class Charge(BaseModel):
    offense: str | None = None
    case_no: str | None = None
    warrant_no: str | None = None
    disposition: str | None = None      # court outcome (DISM, etc.); jail rosters lack it
    extra: dict = Field(default_factory=dict)   # source-specific fields, verbatim


class InmateRecord(BaseModel):
    source: str                          # adapter id, e.g. "tarrant"
    source_url: str | None = None        # deep link back to the source record
    name: str
    year_of_birth: str | None = None
    sex: str | None = None
    booking_date: str | None = None
    photo_base64: str | None = None
    charges: list[Charge] = Field(default_factory=list)
    matched_on: list[MatchInfo] = Field(default_factory=list)
    raw: dict = Field(default_factory=dict)   # everything as scraped, for debug/audit


class AdapterStatus(str, Enum):
    OK = "ok"
    NO_RESULTS = "no_results"
    ERROR = "error"
    TIMEOUT = "timeout"


class AdapterResult(BaseModel):
    """One source's outcome for one search — the unit the orchestrator streams."""

    source: str
    display_name: str
    status: AdapterStatus
    records: list[InmateRecord] = Field(default_factory=list)
    total: int | None = None             # source-reported total (may exceed len(records))
    partial: bool = False                # True when results were capped (time/page budget) — more exist
    duration_ms: int
    error: str | None = None             # human-readable, set when status is ERROR


# ---------------------------------------------------------------------------
# INPUT — the normalized query fanned out to every source
# ---------------------------------------------------------------------------


class Sex(str, Enum):
    MALE = "M"
    FEMALE = "F"
    UNKNOWN = "U"


class SearchQuery(BaseModel):
    """The normalized search input.

    `last` is the only required field — every source searches by surname. The
    optional fields refine the search where a source's form supports them, and are
    used to rank/filter results client-side where it doesn't. (Government search
    fields are dirty — e.g. Dallas DOB is often masked — so we prefer searching
    broad and ranking, over pushing filters into each site. See docs/ARCHITECTURE.)
    """

    last: str
    first: str | None = None
    middle: str | None = None
    sex: Sex | None = None
    year_of_birth: int | None = None
    max_results: int = Field(default=25, ge=1)   # a floor of 1 — 0/negative would break every cap

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.first, self.middle, self.last) if p)


# ---------------------------------------------------------------------------
# CONTRACT — what every source implements, and the context it's handed
# ---------------------------------------------------------------------------


class AdapterContext:
    """Per-search context passed to every adapter.

    Holds the shared, *injectable* transports plus a monotonic clock. Fixture tests
    construct one with an httpx client wired to a MockTransport, so adapter code is
    byte-for-byte identical in production and in tests. Adapters must treat this as
    the only way they reach the outside world — never create their own httpx client
    or Playwright browser.

    `browser` is None for HTTP-tier adapters; Tier-4 browser adapters receive a live
    BrowserManager here (started by the app lifespan and wired in by the orchestrator).
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        timeout_s: float = 20.0,
        browser=None,  # BrowserManager | None  (import kept lazy to avoid circular dep)
    ) -> None:
        self.http = http
        self.timeout_s = timeout_s
        self.browser = browser

    @staticmethod
    def now_ms() -> int:
        """Monotonic milliseconds, for `duration_ms` (elapsed only — not wall time)."""
        return int(time.monotonic() * 1000)


class Adapter(ABC):
    """One per source. Absorbs a site's quirks and returns the normalized shape.

    The class attributes describe the source (set them on the subclass); `search`
    does the work. Two hard rules, enforced by review:
      • Adapters never import each other.
      • `search` never raises — it converts failures into an AdapterResult with
        ERROR/TIMEOUT status, so one bad source can't break the whole run.
    """

    id: str                # "tarrant"
    display_name: str      # "Tarrant County"
    transport: str         # "http" | "browser"
    tier: int              # 1..5, see docs/SOURCES.md
    has_photos: bool = False  # True when this source's detail carries a mugshot (jail rosters) — the
                              # UI auto-loads the photo at search for the identity scan. /api/health
                              # surfaces it so the frontend needn't hardcode which sources have images.
    timeout_s: float | None = None  # optional per-source total budget (seconds); None = engine
                                     # default. Slow court systems (ODCR's cold POST ~16s, Dallas
                                     # paging a common surname ~19s) raise this so they aren't cut
                                     # off mid-search, while fast jail rosters keep the tight default.
    portal_url: str | None = None  # the source's public landing/search page — a stable URL a human
                                    # can open. Many court/jail sites are session- or POST-gated and
                                    # CANNOT expose a per-record deep link (InmateRecord.source_url),
                                    # so the UI falls back to this portal + the case number. /api/health
                                    # surfaces it so the frontend hardcodes no per-source URLs.

    @abstractmethod
    async def search(self, query: SearchQuery, ctx: AdapterContext) -> AdapterResult:
        ...

    async def fetch_detail(self, record_id: str, ctx: AdapterContext) -> InmateRecord | None:
        """Fetch ONE record's full detail by its source id (e.g. Tarrant CID) — the heavy
        per-record pull (mugshot, full charges) done lazily on demand, not for every search row.

        Returns the hydrated record, or None if this source has no extra detail to fetch.
        Default: unsupported. Like `search`, this should not raise — return None on failure.
        """
        return None
