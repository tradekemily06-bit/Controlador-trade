from integration.ecosystem_service import EcosystemService
import pytest

from storage.production_boundary import ProductionStoragePolicy


def test_analyze_is_recorded_and_execution_stays_blocked():
    service = EcosystemService()
    record = service.analyze({"score": 85, "confirmed": True, "filters_ok": True, "symbol": "EURUSD", "timeframe": "5m"})

    assert record.signal == "COMPRA"
    assert record.is_actionable is True
    assert record.execution_allowed is False
    assert len(service.memory_view()) == 1


def test_replay_and_statistics_share_the_same_memory():
    service = EcosystemService()
    results = service.replay([
        {"score": 90, "confirmed": True, "filters_ok": True},
        {"score": 50, "confirmed": False, "filters_ok": True},
    ])

    assert len(results) == 2
    stats = service.statistics()
    assert stats["total"] == 2
    assert stats["actionable"] == 1


def test_system_status_has_safe_gates():
    status = EcosystemService().system_status()

    assert status["mode"] == "SIMULACAO"
    assert status["execution_allowed"] is False
    assert status["real"] == "DESABILITADO"
    assert status["mt5_demo"] == "DEMO_VALIDADO"
    assert status["production_operation_gate"]["authorized"] is False


def test_production_context_requires_subject_and_tenant():
    service = EcosystemService()

    with pytest.raises(PermissionError):
        service.require_production_context(subject_id=None, tenant_id="tenant-a")

    with pytest.raises(PermissionError):
        service.require_production_context(subject_id="user-a", tenant_id=None)


def test_production_context_normalizes_trusted_scope():
    context = EcosystemService().require_production_context(
        subject_id="  user-a  ",
        tenant_id="  tenant-a  ",
    )

    assert context.subject_id == "user-a"
    assert context.tenant_id == "tenant-a"
    assert context.is_valid() is True


def test_production_operation_requires_ready_storage():
    service = EcosystemService()

    with pytest.raises(PermissionError, match="storage is not ready"):
        service.authorize_production_operation(subject_id="user-a", tenant_id="tenant-a")


def test_production_operation_accepts_explicit_ready_storage():
    service = EcosystemService(
        production_storage=ProductionStoragePolicy(
            provider_configured=True,
            tenant_scoped=True,
            durable=True,
        )
    )

    context = service.authorize_production_operation(subject_id="user-a", tenant_id="tenant-a")

    assert context.subject_id == "user-a"
    assert context.tenant_id == "tenant-a"
    assert service.system_status()["real"] == "DESABILITADO"
