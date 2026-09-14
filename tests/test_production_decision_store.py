from __future__ import annotations

import pytest

from analysis.decision_record import DecisionRecord
from storage.production_decision_store import ProductionDecisionStore


class FakeProvider:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str, str], dict] = {}

    def save(self, record: dict, *, tenant_id: str, subject_id: str) -> None:
        self.records[(tenant_id, subject_id, record["decision_id"])] = dict(record)

    def load(self, record_id: str, *, tenant_id: str, subject_id: str):
        return self.records.get((tenant_id, subject_id, record_id))

    def list(self, *, tenant_id: str, subject_id: str, limit: int = 100):
        values = [value for (tenant, subject, _), value in self.records.items() if tenant == tenant_id and subject == subject_id]
        return values[:limit]


def make_record() -> DecisionRecord:
    return DecisionRecord(
        decision_id="d-1",
        created_at="2026-09-14T00:00:00+00:00",
        symbol="EURUSD",
        timeframe="5m",
        signal="COMPRA",
        score=91.0,
        confirmed=True,
        reason="validated",
    )


def test_save_and_load_requires_and_preserves_scope() -> None:
    provider = FakeProvider()
    store = ProductionDecisionStore(provider)
    store.save(make_record(), tenant_id="tenant-a", subject_id="user-a")

    loaded = store.load("d-1", tenant_id="tenant-a", subject_id="user-a")
    assert loaded is not None
    assert loaded.decision_id == "d-1"
    assert loaded.tenant_id == "tenant-a"
    assert loaded.subject_id == "user-a"
    assert store.load("d-1", tenant_id="tenant-b", subject_id="user-a") is None


def test_list_cannot_cross_scope() -> None:
    provider = FakeProvider()
    store = ProductionDecisionStore(provider)
    store.save(make_record(), tenant_id="tenant-a", subject_id="user-a")

    assert [item.decision_id for item in store.list(tenant_id="tenant-a", subject_id="user-a")] == ["d-1"]
    assert store.list(tenant_id="tenant-a", subject_id="user-b") == []


def test_partial_scope_is_rejected() -> None:
    store = ProductionDecisionStore(FakeProvider())
    with pytest.raises(ValueError):
        store.list(tenant_id="tenant-a", subject_id="")
    with pytest.raises(ValueError):
        store.load("d-1", tenant_id="", subject_id="user-a")


def test_provider_scope_violation_fails_closed() -> None:
    provider = FakeProvider()
    store = ProductionDecisionStore(provider)
    record = make_record().with_owner(subject_id="attacker", tenant_id="other")
    provider.save(record.to_dict(), tenant_id="tenant-a", subject_id="user-a")

    with pytest.raises(RuntimeError, match="outside the requested scope"):
        store.load("d-1", tenant_id="tenant-a", subject_id="user-a")
