"""The orchestrator — the brain of one search.

Fans a SearchQuery out to all ENABLED adapters concurrently, isolates failures, enforces
a per-source timeout, and **yields each AdapterResult the moment it lands** (in completion
order — the fast HTTP sources stream in while a slow browser source is still working).
This async generator is what the SSE endpoint iterates.

Source-agnostic by rule: no county names here. It asks the registry for the enabled
adapters and hands each one a shared AdapterContext (one httpx client per search).
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx

from adapters import registry
from adapters.base import (
    Adapter,
    AdapterContext,
    AdapterResult,
    AdapterStatus,
    SearchQuery,
)
from core.audit import AuditLog

_DEFAULT_TIMEOUT_S = 20.0
# An office-machine-looking UA; the on-prem box is a real network, not a datacenter.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
)


async def run_search(
    query: SearchQuery,
    *,
    adapters: list[Adapter] | None = None,
    audit: AuditLog | None = None,
    staff: str | None = None,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> AsyncIterator[AdapterResult]:
    """Yield one AdapterResult per source, in completion order (fastest first).

    `adapters` defaults to the registry's enabled set; tests pass an explicit list.
    Every search is audited (if an audit log is given) before any source is hit.
    """
    sources = adapters if adapters is not None else registry.enabled_adapters()

    if audit is not None:
        audit.log_search(query, [a.id for a in sources], staff=staff)
    if not sources:
        return

    # Per-source budget: a slow court system can declare `timeout_s` to get more than the fast
    # default (an adapter that doesn't declare one keeps `timeout_s`). The shared client's timeout
    # is the widest budget so a long request isn't cut prematurely — each source is still governed
    # by its own `wait_for` below, and one slow source never blocks the others (completion-order).
    budgets = {a.id: (a.timeout_s or timeout_s) for a in sources}
    client_timeout = max([timeout_s, *budgets.values()])

    async with httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT},
        follow_redirects=True,
        timeout=httpx.Timeout(client_timeout),
    ) as client:
        pending = [
            _run_one(a, query, AdapterContext(client, timeout_s=budgets[a.id]), budgets[a.id])
            for a in sources
        ]
        for completed in asyncio.as_completed(pending):
            yield await completed


async def _run_one(
    adapter: Adapter, query: SearchQuery, ctx: AdapterContext, timeout_s: float
) -> AdapterResult:
    """Run one adapter with a hard outer timeout + failure isolation. Never raises.

    Adapters already catch their own errors, but this is the safety net: a hung adapter
    is cancelled at `timeout_s` (TIMEOUT), and a contract-breaking raise becomes ERROR —
    so one bad source can never take down the whole search.
    """
    start = AdapterContext.now_ms()
    try:
        return await asyncio.wait_for(adapter.search(query, ctx), timeout=timeout_s)
    except (asyncio.TimeoutError, TimeoutError):
        return AdapterResult(
            source=adapter.id,
            display_name=adapter.display_name,
            status=AdapterStatus.TIMEOUT,
            duration_ms=AdapterContext.now_ms() - start,
        )
    except Exception as e:  # defensive: adapters shouldn't raise, but never trust that
        return AdapterResult(
            source=adapter.id,
            display_name=adapter.display_name,
            status=AdapterStatus.ERROR,
            error=str(e),
            duration_ms=AdapterContext.now_ms() - start,
        )
