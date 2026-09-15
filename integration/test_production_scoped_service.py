from __future__ import annotations

import pytest

from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService
from integration.production_data_plane import ProductionDataPlane
from storage.production_provider import ProductionProviderConfig


def _plane(tmp_path):
    plane = ProductionDataPlane.from_config(
        ProductionProviderConfig(provider="sqlite", database_path=str(tmp_path / "production.db"), multi_instance=False)
    )
    assert plane is not None
    return plane


def _payload(score: float = 91):
    return {
        "score": score,
        "confirmed": True,
        "filters_ok": True,
        "symbol": "EURUSD",
        "timeframe": "M5",
    }


def test_configured_service_uses_durable_scope_for_analysis_memory_and_statistics(tmp_path) -> None:
    plane = _plane(tmp_path)
    service = ConfiguredEcosystemService(production_data_plane=plane)

    record = service.analyze(_payload(), subject_id="user-a", tenant_id="tenant-a")

    assert service.memory_view(subject_id="user-a", tenant_id="tenant-a")[0]["decision_id"] == record.decision_id
    assert service.memory_view(subject_id="user-b", tenant_id="tenant-a") == []
    assert service.memory_view(subject_id="user-a", tenant_id="tenant-b") == []
    assert service.statistics(subject_id="user-a", tenant_id="tenant-a")["total"] == 1
    assert service.statistics(subject_id="user-b", tenant_id="tenant-a")["total"] == 0
    assert service.production_storage.status()["status"] == "READY"
    assert service.production_gate.status()["storage_state"] == "READY"

    restarted = ConfiguredEcosystemService(production_data_plane=plane)
    assert restarted.memory_view(subject_id="user-a", tenant_id="tenant-a")[0]["decision_id"] == record.decision_id


def test_outcome_update_uses_durable_record_not_process_memory(tmp_path) -> None:
    plane = _plane(tmp_path)
    writer = ConfiguredEcosystemService(production_data_plane=plane)
    record = writer.analyze(_payload(), subject_id="user-a", tenant_id="tenant-a")

    reader = ConfiguredEcosystemService(production_data_plane=plane)
    updated = reader.record_outcome(record.decision_id, "WIN", subject_id="user-a", tenant_id="tenant-a")

    assert updated.outcome == "WIN"
    persisted = reader.memory_view(subject_id="user-a", tenant_id="tenant-a")
    assert persisted[0]["outcome"] == "WIN"


def test_public_saas_without_provider_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("CONTROLADOR_SAAS_PUBLIC", "true")
    service = ConfiguredEcosystemService()

    with pytest.raises(RuntimeError, match="production storage provider"):
        service.analyze(_payload(), subject_id="user-a", tenant_id="tenant-a")


def test_production_service_never_reads_global_process_memory(tmp_path) -> None:
    plane = _plane(tmp_path)
    service = ConfiguredEcosystemService(production_data_plane=plane)
    service.memory.append(service.analyze(_payload(80), persist=False, subject_id="user-a", tenant_id="tenant-a"))

    assert service.memory_view(subject_id="user-b", tenant_id="tenant-a") == []
