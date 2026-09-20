from __future__ import annotations

import pytest

from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService
from integration.production_data_plane import ProductionDataPlane
from security.http_identity import clear_trusted_identity, require_trusted_identity
from storage.production_provider import ProductionProviderConfig


def _plane(tmp_path):
    plane = ProductionDataPlane.from_config(
        ProductionProviderConfig(provider="sqlite", database_path=str(tmp_path / "production.db"), multi_instance=False)
    )
    assert plane is not None
    return plane


def _payload(score: float = 91):
    candles = []
    closes = (1.1000, 1.1008, 1.1011, 1.1006, 1.1014, 1.1020, 1.1017, 1.1024)
    for index, close in enumerate(closes):
        timestamp = f"2026-09-15T00:0{index}:00+00:00"
        candles.append(
            {
                "open": close - 0.0004,
                "high": close + 0.0006,
                "low": close - 0.0007,
                "close": close,
                "timestamp": timestamp,
            }
        )
    return {
        "score": score,
        "confirmed": True,
        "filters_ok": True,
        "symbol": "EURUSD",
        "timeframe": "M5",
        "candles": candles,
        "available_nodes": ["market_data", "price_history", "risk", "execution", "security"],
        "observed_nodes": ["market_data", "price_history", "risk", "execution", "security"],
        "relationships_reviewed": ["market_data->risk", "price_history->risk", "risk->execution", "security->execution"],
    }


def _identity(tenant_id: str = "tenant-a", subject_id: str = "user-a") -> None:
    require_trusted_identity(
        {
            "PATH_INFO": "/api/test",
            "controlador.trusted_tenant_id": tenant_id,
            "controlador.trusted_subject_id": subject_id,
            "controlador.trusted_role": "user",
        }
    )


def test_configured_service_uses_durable_scope_for_analysis_memory_and_statistics(tmp_path) -> None:
    plane = _plane(tmp_path)
    service = ConfiguredEcosystemService(production_data_plane=plane)
    _identity()
    try:
        record = service.analyze(_payload(), subject_id="user-a", tenant_id="tenant-a")

        assert service.memory_view(subject_id="user-a", tenant_id="tenant-a")[0]["decision_id"] == record.decision_id
        with pytest.raises(PermissionError):
            service.memory_view(subject_id="user-b", tenant_id="tenant-a")
        with pytest.raises(PermissionError):
            service.memory_view(subject_id="user-a", tenant_id="tenant-b")
        assert service.statistics(subject_id="user-a", tenant_id="tenant-a")["total"] == 1
        assert service.production_storage.status()["status"] == "READY"
        assert service.production_gate.status()["storage_state"] == "READY"

        restarted = ConfiguredEcosystemService(production_data_plane=plane)
        assert restarted.memory_view(subject_id="user-a", tenant_id="tenant-a")[0]["decision_id"] == record.decision_id
    finally:
        clear_trusted_identity()


def test_outcome_update_uses_durable_record_not_process_memory(tmp_path) -> None:
    plane = _plane(tmp_path)
    writer = ConfiguredEcosystemService(production_data_plane=plane)
    _identity()
    try:
        record = writer.analyze(_payload(), subject_id="user-a", tenant_id="tenant-a")

        reader = ConfiguredEcosystemService(production_data_plane=plane)
        updated = reader.record_outcome(record.decision_id, "WIN", subject_id="user-a", tenant_id="tenant-a")

        assert updated.outcome == "WIN"
        persisted = reader.memory_view(subject_id="user-a", tenant_id="tenant-a")
        assert persisted[0]["outcome"] == "WIN"
    finally:
        clear_trusted_identity()


def test_public_saas_without_provider_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("CONTROLADOR_SAAS_PUBLIC", "true")
    service = ConfiguredEcosystemService()
    _identity()
    try:
        with pytest.raises(RuntimeError, match="production storage provider"):
            service.analyze(_payload(), subject_id="user-a", tenant_id="tenant-a")
    finally:
        clear_trusted_identity()


def test_production_service_never_reads_global_process_memory(tmp_path) -> None:
    plane = _plane(tmp_path)
    service = ConfiguredEcosystemService(production_data_plane=plane)
    _identity()
    try:
        with pytest.raises(RuntimeError, match="local learning state is unavailable"):
            service.memory.append(service.analyze(_payload(80), persist=False, subject_id="user-a", tenant_id="tenant-a"))

        with pytest.raises(PermissionError):
            service.memory_view(subject_id="user-b", tenant_id="tenant-a")
    finally:
        clear_trusted_identity()


def test_production_service_replaces_legacy_local_store_with_fail_closed_block(tmp_path) -> None:
    plane = _plane(tmp_path)
    service = ConfiguredEcosystemService(production_data_plane=plane)

    with pytest.raises(RuntimeError, match="local learning state is unavailable"):
        len(service.memory)
    with pytest.raises(RuntimeError, match="local decision store is unavailable"):
        service.store.load()
    with pytest.raises(RuntimeError, match="local decision store is unavailable"):
        service.store.save_many([])


def test_production_service_cannot_retain_preloaded_legacy_decisions(tmp_path) -> None:
    class LegacyStore:
        def load(self):
            return ["legacy-local-record"]

        def save(self, _record):
            raise AssertionError("legacy store write must not be authoritative")

        def save_many(self, _records):
            raise AssertionError("legacy store write must not be authoritative")

    plane = _plane(tmp_path)
    service = ConfiguredEcosystemService(decision_store=LegacyStore(), production_data_plane=plane)

    with pytest.raises(RuntimeError, match="local learning state is unavailable"):
        len(service.memory)
    with pytest.raises(RuntimeError, match="local decision store is unavailable"):
        service.store.save(object())
