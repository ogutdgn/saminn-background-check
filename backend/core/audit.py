"""Append-only audit log (SQLite).

This tool searches criminal-record PII, so every search is recorded — who, what name,
when, which sources ran. The log is **append-only** (INSERT only; never UPDATE/DELETE)
and is never casually purged. The DB file lives on the on-prem box and is git-ignored.

Staff identity is nullable for now (the auth decision is deferred); when auth lands, the
caller passes `staff` so entries are attributable.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from adapters.base import SearchQuery

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT    NOT NULL,   -- ISO-8601 UTC
    staff      TEXT,               -- who searched (nullable until auth lands)
    query_last TEXT    NOT NULL,
    query_full TEXT,
    sources    TEXT    NOT NULL    -- comma-joined adapter ids that ran
);
"""


class AuditLog:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def log_search(self, query: SearchQuery, source_ids: list[str], *, staff: str | None = None) -> None:
        self._conn.execute(
            "INSERT INTO audit_log (ts, staff, query_last, query_full, sources) VALUES (?, ?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(),
                staff,
                query.last,
                query.full_name,
                ",".join(source_ids),
            ),
        )
        self._conn.commit()

    def recent(self, limit: int = 50) -> list[dict]:
        cur = self._conn.execute(
            "SELECT ts, staff, query_last, query_full, sources FROM audit_log ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def close(self) -> None:
        self._conn.close()
