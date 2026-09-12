from __future__ import annotations

import unittest

from analysis.decision_record import DecisionRecord
from storage.tenant_decision_repository import ProductionTenantDecisionRepository


class FakeProductionStore:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], dict] = {}

    def save(self, record: dict, *, tenant_id: str) -> None:
        self.records[(tenant_id, record["decision_id"])] = dict(record)

    def load(self, record_id: str, *, tenant_id: str) -> dict | None:
        return self.records.get((tenant_id, record_id))

    def list(self, *, tenant_id: str, limit: int = 100) -> list[dict]:
        items = [record for (scope, _), record in self.records.items() if scope == tenant_id]
        return items[:limit]


def sample_record(decision_id: str) -> DecisionRecord:
    return DecisionRecord(
        decision_id=decision_id,
        created_at="2026-09-12T00:00:00+00:00",
        symbol="BTCUSD",
        timeframe="5m",
        signal="COMPRA",
        score=90.0,
        confirmed=True,
        reason="confirmed",
    )


class TenantDecisionRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = FakeProductionStore()
        self.repository = ProductionTenantDecisionRepository(self.store)

    def test_save_and_load_are_scoped_to_tenant(self) -> None:
        record = sample_record("decision-1")
        self.repository.save(record, tenant_id="tenant-a")

        self.assertEqual(self.repository.load("decision-1", tenant_id="tenant-a"), record)
        self.assertIsNone(self.repository.load("decision-1", tenant_id="tenant-b"))

    def test_list_never_returns_another_tenant(self) -> None:
        self.repository.save(sample_record("a"), tenant_id="tenant-a")
        self.repository.save(sample_record("b"), tenant_id="tenant-b")

        self.assertEqual([item.decision_id for item in self.repository.list(tenant_id="tenant-a")], ["a"])
        self.assertEqual([item.decision_id for item in self.repository.list(tenant_id="tenant-b")], ["b"])

    def test_tenant_and_decision_id_are_required(self) -> None:
        with self.assertRaises(ValueError):
            self.repository.save(sample_record("x"), tenant_id=" ")
        with self.assertRaises(ValueError):
            self.repository.load(" ", tenant_id="tenant-a")

    def test_limit_is_validated(self) -> None:
        with self.assertRaises(ValueError):
            self.repository.list(tenant_id="tenant-a", limit=0)
        with self.assertRaises(ValueError):
            self.repository.list(tenant_id="tenant-a", limit=True)


if __name__ == "__main__":
    unittest.main()
