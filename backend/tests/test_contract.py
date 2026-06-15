"""Sanity checks on the shared contract (the keystone).

These don't test any source — they pin the *shape*: required fields, safe mutable
defaults, enum-to-string serialization (which the SSE endpoint + generated frontend
types depend on), and the registry. Per-source parsing tests live in test_<county>.py.
"""
from adapters import registry
from adapters.base import (
    AdapterResult,
    AdapterStatus,
    Charge,
    InmateRecord,
    MatchInfo,
    MatchType,
    SearchQuery,
    Sex,
)


def test_minimal_record_only_needs_source_and_name():
    r = InmateRecord(source="tarrant", name="SMITH, AARON")
    # everything optional defaults safely
    assert r.year_of_birth is None
    assert r.photo_base64 is None
    assert r.charges == [] and r.matched_on == [] and r.raw == {}


def test_mutable_defaults_are_not_shared():
    a = InmateRecord(source="s", name="A")
    b = InmateRecord(source="s", name="B")
    a.charges.append(Charge(offense="THEFT"))
    a.raw["k"] = 1
    assert b.charges == [] and b.raw == {}  # default_factory, not a shared instance


def test_search_query_requires_only_last():
    q = SearchQuery(last="smith")
    assert q.first is None and q.full_name == "smith"
    q2 = SearchQuery(last="smith", first="john", middle="q", sex=Sex.MALE, year_of_birth=1990)
    assert q2.full_name == "john q smith"


def test_adapter_result_serializes_enums_to_strings():
    # The SSE stream and OpenAPI-generated TS types rely on enums dumping to strings.
    res = AdapterResult(
        source="dallas",
        display_name="Dallas County",
        status=AdapterStatus.OK,
        records=[
            InmateRecord(
                source="dallas",
                name="SMITH, JOHN",
                matched_on=[MatchInfo(type=MatchType.NAME)],
                charges=[Charge(offense="THEFT", case_no="MC1", disposition="DISM")],
            )
        ],
        total=1,
        duration_ms=12,
    )
    data = res.model_dump(mode="json")
    assert data["status"] == "ok"
    assert data["records"][0]["matched_on"][0]["type"] == "name"
    assert data["records"][0]["charges"][0]["disposition"] == "DISM"


def test_registry_starts_empty_and_nothing_enabled():
    assert registry.all_adapters() == []
    assert registry.enabled_adapters() == []
