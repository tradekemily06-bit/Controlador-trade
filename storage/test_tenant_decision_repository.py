from __future__ import annotations

import unittest

from analysis.decision_record import DecisionRecord
from storage.tenant_decision_repository import ProductionTenantDecisionRepository


class FakeProductionStore:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str, str], dict] = {}

    def save(self, record: dict, *, tenant_id: str, subject_id: str) -> None:
        self.records[(tenant_id, subject_id, record["decision_id"])] = dict(record)

    def load(self, record_id: str, *, tenant_id: str, subject_id: str) -> dict | None:
        return self.records.get((tenant_id, subject_id, record_id))

    def list(self, *, tenant_id: str, subject_id: str, limit: int = 100) -> list[dict]:
        items = [record for (scope, owner, _), record in self.records.items() if scope == tenant_id and owner == subject_id]
        return items[:limit]


def sample_record(decision_id: str, *, tenant_id: str = "tenant-a", subject_id: str = "user-a") -> DecisionRecord:
    return DecisionRecord(
        decision_id=decision_id,
        created_at="2026-09-12T00:00:00+00:00",
        symbol="BTCUSD",
        timeframe="5m",
        signal="COMPRA",
        score=90.0,
        confirmed=True,
        reason="confirmed",
        subject_id=subject_id,
        tenant_id=tenant_id,
    )


class TenantDecisionRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = FakeProductionStore()
        self.repository = ProductionTenantDecisionRepository(self.store)

    def test_save_and_load_are_scoped_to_tenant_and_subject(self) -> None:
        record = sample_record("decision-1")
        self.repository.save(record, tenant_id="tenant-a", subject_id="user-a")

        self.assertEqual(self.repository.load("decision-1", tenant_id="tenant-a", subject_id="user-a"), record)
        self.assertIsNone(self.repository.load("decision-1", tenant_id="tenant-b", subject_id="user-b"))
        with self.assertRaises(PermissionError):
            self.repository.load("decision-1", tenant_id="tenant-a", subject_id="user-b")

    def test_list_never_returns_another_tenant_or_subject(self) -> None:
        self.repository.save(sample_record("a"), tenant_id="tenant-a", subject_id="user-a")
        self.repository.save(sample_record("other-user", tenant_id="tenant-a", subject_id="user-b"), tenant_id="tenant-a", subject_id="user-b")
        self.repository.save(sample_record("other-tenant", tenant_id="tenant-b", subject_id="user-b"), tenant_id="tenant-b", subject_id="user-b")

        self.assertEqual([item.decision_id for item in self.repository.list(tenant_id="tenant-a", subject_id="user-a")], ["a"])
        self.assertEqual([item.decision_id for item in self.repository.list(tenant_id="tenant-a", subject_id="user-b")], ["other-user"])
        self.assertEqual([item.decision_id for item in self.repository.list(tenant_id="tenant-b", subject_id="user-b")], ["other-tenant"])

    def test_owner_and_tenant_must_match_on_save(self) -> None:
        with self.assertRaises(PermissionError):
            self.repository.save(sample_record("x", tenant_id="tenant-a"), tenant_id="tenant-b", subject_id="user-a")
        with self.assertRaises(PermissionError):
            self.repository.save(sample_record("y", subject_id="user-a"), tenant_id="tenant-a", subject_id="user-b")

    def test_core_fields_cannot_be_overwritten_but_outcome_can_change(self) -> None:
        original = sample_record("immutable")
        self.repository.save(original, tenant_id="tenant-a", subject_id="user-a")

        closed = original.with_outcome("WIN")
        self.repository.save(closed, tenant_id="tenant-a", subject_id="user-a")
        self.assertEqual(self.repository.load("immutable", tenant_id="tenant-a", subject_id="user-a").outcome, "WIN")

        tampered = DecisionRecord(**{**closed.to_dict(), "score": 1.0})
        with self.assertRaises(PermissionError):
            self.repository.save(tampered, tenant_id="tenant-a", subject_id="user-a")

    def test_stored_record_without_owner_fails_closed(self) -> None:
        self.store.records[("tenant-a", "user-a", "legacy")] = sample_record("legacy").to_dict() | {"subject_id": None}
        with self.assertRaises(PermissionError):
            self.repository.load("legacy", tenant_id="tenant-a", subject_id="user-a")

    def test_tenant_subject_and_decision_id_are_required(self) -> None:
        with self.assertRaises(ValueError):
            self.repository.save(sample_record("x"), tenant_id=" ", subject_id="user-a")
        with self.assertRaises(ValueError):
            self.repository.save(sample_record("x"), tenant_id="tenant-a", subject_id=" ")
        with self.assertRaises(ValueError):
            self.repository.load(" ", tenant_id="tenant-a", subject_id="user-a")

    def test_limit_is_validated(self) -> None:
        with self.assertRaises(ValueError):
            self.repository.list(tenant_id="tenant-a", subject_id="user-a", limit=0)
        with self.assertRaises(ValueError):
            self.repository.list(tenant_id="tenant-a", subject_id="user-a", limit=True)


if __name__ == "__main__":
    unittest.main()
