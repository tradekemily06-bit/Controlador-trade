from __future__ import annotations

import pytest

from analysis.decision_record import DecisionRecord
from core.models import AnalysisResult, Signal
from integration.production_data_plane import ProductionDataPlane
from storage.production_provider import ProductionProviderConfig


def _record() -> DecisionRecord:
    return DecisionRecord.from_analysis(
        AnalysisResult(signal=Signal.COMPRA, score=91, reason="validated", confirmed=True)
    )


def test_unconfigured_provider_does_not_create_a_local_fallback() -> None:
    plane = ProductionDataPlane.from_config(
        ProductionProviderConfig(provider="", database_path=None, multi_instance=False)
    )
    assert plane is None


def test_production_data_plane_requires_complete_scope(tmp_path) -> None:
    plane = ProductionDataPlane.from_config(
        ProductionProviderConfig(provider="sqlite", database_path=str(tmp_path / "production.db"), multi_instance=False)
    )
    assert plane is not None
    with pytest.raises(PermissionError):
        plane.save(_record(), tenant_id="tenant-a", subject_id=None)
    with pytest.raises(PermissionError):
        plane.list(tenant_id=None, subject_id="user-a")


def test_production_data_plane_persists_only_in_requested_scope(tmp_path) -> None:
    plane = ProductionDataPlane.from_config(
        ProductionProviderConfig(provider="sqlite", database_path=str(tmp_path / "production.db"), multi_instance=False)
    )
    assert plane is not None
    record = _record()
    plane.save(record, tenant_id="tenant-a", subject_id="user-a")

    own = plane.list(tenant_id="tenant-a", subject_id="user-a")
    other_user = plane.list(tenant_id="tenant-a", subject_id="user-b")
    other_tenant = plane.list(tenant_id="tenant-b", subject_id="user-a")

    assert len(own) == 1
    assert own[0].decision_id == record.decision_id
    assert other_user == []
    assert other_tenant == []


def test_sqlite_production_plane_remains_single_instance_only(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="multi-instance"):
        ProductionDataPlane.from_config(
            ProductionProviderConfig(provider="sqlite", database_path=str(tmp_path / "production.db"), multi_instance=True)
        )
