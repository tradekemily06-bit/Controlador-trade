from __future__ import annotations

import pytest

from analysis.decision_record import DecisionRecord
from integration.production_data_plane import ProductionDataPlane
from integration.production_scoped_service import ProductionScopedServiceMixin
from security.http_identity import clear_trusted_identity, require_trusted_identity
from storage.production_provider import ProductionProviderConfig


class _ScopedProbe(ProductionScopedServiceMixin):
    def __init__(self, plane):
        self.memory = []
        self.production_data_plane = plane


def _identity(tenant: str, subject: str):
    require_trusted_identity({
        "PATH_INFO": "/api/test",
        "controlador.trusted_tenant_id": tenant,
        "controlador.trusted_subject_id": subject,
        "controlador.trusted_role": "user",
    })


def _record(index: int, tenant: str, subject: str) -> DecisionRecord:
    return DecisionRecord(
        decision_id=f"decision-{index}",
        created_at=f"2026-01-01T00:00:{index:02d}+00:00",
        symbol="EURUSD",
        timeframe="M5",
        signal="COMPRA",
        score=90,
        confirmed=True,
        reason="validated",
        execution_allowed=False,
        outcome="WIN",
        tenant_id=tenant,
        subject_id=subject,
    )


def test_production_store_has_no_hidden_history_cap(tmp_path):
    config = ProductionProviderConfig(provider="sqlite", database_path=str(tmp_path / "production.db"), multi_instance=False)
    plane = ProductionDataPlane.from_config(config)
    _identity("tenant-a", "user-a")
    try:
        for index in range(150):
            plane.save(_record(index, "tenant-a", "user-a"), tenant_id="tenant-a", subject_id="user-a")
        assert len(plane.list(tenant_id="tenant-a", subject_id="user-a", limit=None)) == 150
        assert len(plane.list(tenant_id="tenant-a", subject_id="user-a", limit=25)) == 25
    finally:
        clear_trusted_identity()


def test_production_scope_rejects_browser_supplied_foreign_owner(tmp_path):
    config = ProductionProviderConfig(provider="sqlite", database_path=str(tmp_path / "production.db"), multi_instance=False)
    plane = ProductionDataPlane.from_config(config)
    probe = _ScopedProbe(plane)
    _identity("tenant-a", "user-a")
    try:
        with pytest.raises(PermissionError):
            probe._production_records(type("Owner", (), {"tenant_id": "tenant-b", "subject_id": "user-b"})())
    finally:
        clear_trusted_identity()


def test_production_provider_isolates_cross_tenant_history(tmp_path):
    config = ProductionProviderConfig(provider="sqlite", database_path=str(tmp_path / "production.db"), multi_instance=False)
    plane = ProductionDataPlane.from_config(config)
    _identity("tenant-a", "user-a")
    try:
        plane.save(_record(1, "tenant-a", "user-a"), tenant_id="tenant-a", subject_id="user-a")
        plane.save(_record(2, "tenant-b", "user-b"), tenant_id="tenant-b", subject_id="user-b")
        own = plane.list(tenant_id="tenant-a", subject_id="user-a", limit=None)
        assert [item.decision_id for item in own] == ["decision-1"]
    finally:
        clear_trusted_identity()
