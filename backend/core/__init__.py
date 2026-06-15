"""The engine — source-agnostic machinery every adapter relies on.

orchestrator (fan-out + stream), audit (append-only log). browser manager + cache are
added when a source needs them. `core` depends on the contract (adapters/base.py) and
the registry, but never on a specific county adapter. See backend/core/README.md.
"""
