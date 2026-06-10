# backend/adapters/

**One file per source.** This is the heart of the system and the reason the team
scales: each county is an independent adapter behind a shared contract, so five
people build five counties at once without colliding.

## What lives here

| File | Purpose | Exists yet? |
| --- | --- | --- |
| `base.py` | The shared contract: `InmateRecord`, `AdapterResult`, `Adapter` ABC, etc. **The keystone.** Created in Phase 1; changes go through the lead. | Phase 1 |
| `registry.py` | The list of implemented adapters and whether each is enabled. Adding a source = one line here. | Phase 1 |
| `<county>.py` | One adapter per source (e.g. `tarrant.py`). Created when that county is built, per the pipeline. | Per source |

The contract spec is in [`../../docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md).

## Adapter template (shape — actual `base.py` created in Phase 1)

```python
from .base import Adapter, AdapterResult, AdapterStatus, SearchQuery, AdapterContext
from .base import InmateRecord, Charge, MatchInfo, MatchType

class <County>Adapter(Adapter):
    id = "<county>"
    display_name = "<County> County"
    transport = "http"      # or "browser"
    tier = <1-5>

    async def search(self, query: SearchQuery, ctx: AdapterContext) -> AdapterResult:
        start = ctx.now_ms()
        try:
            # 1. pull (httpx for http; ctx.browser for browser sources)
            # 2. parse rows
            # 3. map → InmateRecord, fill charges, populate matched_on
            # 4. return AdapterResult(status=OK|NO_RESULTS, records=..., ...)
            ...
        except TimeoutError:
            return AdapterResult(source=self.id, display_name=self.display_name,
                                 status=AdapterStatus.TIMEOUT, duration_ms=ctx.now_ms()-start)
        except Exception as e:
            return AdapterResult(source=self.id, display_name=self.display_name,
                                 status=AdapterStatus.ERROR, error=str(e),
                                 duration_ms=ctx.now_ms()-start)
```

## Rules

- **No cross-adapter imports.** Adapters never depend on each other.
- **Always populate `matched_on`** (real name vs alias vs attorney) — see why in
  the architecture doc.
- **Fail loudly.** Never silently return unfiltered or page-1-only data; return an
  `ERROR` status with a clear message instead.
- Build by following [`../../docs/ADDING_A_SOURCE.md`](../../docs/ADDING_A_SOURCE.md)
  and pass the Adapter checklist there.
