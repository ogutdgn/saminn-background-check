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


@dataclass
class RegistryEntry:
    adapter: Adapter
    enabled: bool = False


# One line per source, added as each is built. Disabled until it goes live, e.g.:
#     from .tarrant import TarrantAdapter
#     RegistryEntry(TarrantAdapter()),                 # disabled (Stage 2)
#     RegistryEntry(TarrantAdapter(), enabled=True),   # live     (Stage 4)
REGISTRY: list[RegistryEntry] = [
]


def all_adapters() -> list[Adapter]:
    """Every registered adapter, regardless of enabled state."""
    return [e.adapter for e in REGISTRY]


def enabled_adapters() -> list[Adapter]:
    """The adapters the orchestrator should actually fan out to."""
    return [e.adapter for e in REGISTRY if e.enabled]
