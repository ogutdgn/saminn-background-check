"""The source registry — the one place that knows which adapters exist and whether
each is enabled.

The orchestrator asks the registry for the *enabled* adapters; it never imports
adapters directly. This file is the single allowed exception to "no module knows
all the sources" — adding a source is a one-line entry here.

Per the add-a-source pipeline (docs/ADDING_A_SOURCE.md), an adapter is registered
DISABLED first (Stage 2) and flipped to enabled only at Stage 4, once it's live.
"""
from __future__ import annotations

from dataclasses import dataclass

from .base import Adapter
from .collin import CollinAdapter
from .dallas import DallasAdapter
from .denton import DentonAdapter
from .denton_dc import DentonDCAdapter
from .hunt import HuntAdapter
from .odcr import OdcrAdapter
from .tarrant import TarrantAdapter


@dataclass
class RegistryEntry:
    adapter: Adapter
    enabled: bool = False


# One line per source, added as each is built. Disabled until it goes live (Stage 4),
# i.e. flip to `enabled=True` once it's verified end-to-end in the running app.
REGISTRY: list[RegistryEntry] = [
    RegistryEntry(TarrantAdapter(), enabled=True),   # Stage 4 — live
    RegistryEntry(DallasAdapter(), enabled=True),    # Stage 4 — live (pagination handled)
    # ODCR: DISABLED (2026-10-05). odcr.com now answers automated requests with a Cloudflare
    # block page (403 "Sorry, you have been blocked") while real browsers pass — getting around
    # it would break responsible-use rule 3. Re-enable only if plain requests work again.
    RegistryEntry(OdcrAdapter(), enabled=False),
    RegistryEntry(HuntAdapter(), enabled=True),      # Stage 4 — live (current-custody roster; client-side surname filter)
    RegistryEntry(DentonAdapter(), enabled=True),    # Stage 4 — live (Tier-3 Tyler Public Access; stateful VIEWSTATE)
    # Collin: DISABLED. Its Incapsula bot-protection is only passed via playwright-stealth
    # fingerprint patching — WAF evasion, which responsible-use rule 3 forbids (docs/ARCHITECTURE.md).
    # Out of scope until a legitimate public door (or county permission) exists.
    RegistryEntry(CollinAdapter(), enabled=False),
    RegistryEntry(DentonDCAdapter(), enabled=True),  # Stage 4 — live (Tier-3 Tyler PublicAccessDC; District Court felonies)
]


def all_adapters() -> list[Adapter]:
    """Every registered adapter, regardless of enabled state."""
    return [e.adapter for e in REGISTRY]


def enabled_adapters() -> list[Adapter]:
    """The adapters the orchestrator should actually fan out to."""
    return [e.adapter for e in REGISTRY if e.enabled]
