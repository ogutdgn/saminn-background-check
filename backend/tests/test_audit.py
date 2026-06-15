"""Audit log — append-only, persists, reads newest-first."""
from adapters.base import SearchQuery
from core.audit import AuditLog


def test_logs_and_reads_back_newest_first(tmp_path):
    log = AuditLog(tmp_path / "audit.sqlite")
    log.log_search(SearchQuery(last="smith", first="john"), ["tarrant", "dallas"], staff="intake1")
    log.log_search(SearchQuery(last="doe"), ["tarrant"])

    rows = log.recent()
    assert len(rows) == 2
    assert rows[0]["query_last"] == "doe"            # newest first
    assert rows[1]["query_full"] == "john smith"
    assert rows[1]["sources"] == "tarrant,dallas"
    assert rows[1]["staff"] == "intake1"
    assert rows[0]["staff"] is None                  # nullable until auth lands
    assert rows[0]["ts"]                             # timestamp recorded
    log.close()


def test_append_only_history_persists_across_reopen(tmp_path):
    db = tmp_path / "a.sqlite"
    first = AuditLog(db)
    first.log_search(SearchQuery(last="x"), ["t"])
    first.close()

    second = AuditLog(db)               # reopen the same file
    second.log_search(SearchQuery(last="y"), ["t"])
    assert len(second.recent()) == 2    # prior entry is still there
    second.close()
