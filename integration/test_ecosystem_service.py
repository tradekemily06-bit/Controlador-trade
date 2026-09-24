from datetime import datetime, timedelta, timezone

from integration.ecosystem_service import EcosystemService
import pytest

from core.senior_risk_reasoning import RiskDomain, RiskObservation
from data.models import Candle
from core.p122_broker_market_data import BrokerMarketDataSnapshot
from storage.production_boundary import ProductionStoragePolicy


def _candles(count=5):
    base = datetime(2026, 9, 13, tzinfo=timezone.utc)
    return tuple(
        Candle(base + timedelta(minutes=i), 100 + i, 102 + i, 99 + i, 101 + i, 1000 + i)
        for i in range(count)
    )


def test_analyze_is_recorded_and_execution_stays_blocked():
    service = EcosystemService()
    record = service.analyze({"score": 85, "confirmed": True, "filters_ok": True, "symbol": "EURUSD", "timeframe": "5m"})

    assert record.signal == "COMPRA"
    assert record.is_actionable is True
    assert record.execution_allowed is False
    assert len(service.memory_view()) == 1


def test_service_exposes_integrated_senior_context_without_execution_authority():
    service = EcosystemService()
    cycle = service.assess_senior_context(
        context_id="ctx-service-1",
        candles=_candles(),
        available_nodes=("price", "structure", "volatility", "liquidity"),
        observed_nodes=("price", "structure", "volatility", "liquidity"),
        relationships_reviewed=("price-structure", "structure-volatility", "price-liquidity"),
        risk_observations=(
            RiskObservation(RiskDomain.CAPITAL, "Capital observado.", True, ("account",)),
        ),
        available_risk_domains=(RiskDomain.CAPITAL,),
    )

    assert cycle.quality.value == "COMPLETE"
    assert cycle.whole_graph.complete is True
    assert cycle.market_reading.observations
    assert cycle.senior_assessment.questions
    assert cycle.risk_assessment.questions
    assert cycle.execution_authorized is False
    assert cycle.senior_assessment.execution_authorized is False
    assert cycle.risk_assessment.execution_authorized is False


def test_service_keeps_incomplete_senior_context_in_reassessment():
    cycle = EcosystemService().assess_senior_context(
        context_id="ctx-service-2",
        candles=_candles(),
        available_nodes=("price", "structure"),
        observed_nodes=("price", "structure"),
        relationships_reviewed=("price-structure",),
        available_risk_domains=(RiskDomain.CAPITAL,),
    )

    assert cycle.quality.value == "REASSESS"
    assert cycle.execution_authorized is False


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


def test_evaluate_market_snapshot_is_side_effect_free_for_candidate_selection():
    service = EcosystemService()
    candles = _candles(30)
    snapshot = BrokerMarketDataSnapshot(
        symbol="EURUSD",
        timeframe="5m",
        candles=candles,
        source="test",
        received_at=datetime.now(timezone.utc),
    )

    result = service.evaluate_market_snapshot(snapshot)

    assert result.symbol == "EURUSD"
    assert result.timeframe == "5m"
    assert len(service.memory_view()) == 0


def test_record_market_analysis_deduplicates_same_closed_candle():
    service = EcosystemService()
    snapshot = BrokerMarketDataSnapshot(
        symbol="EURUSD",
        timeframe="5m",
        candles=_candles(30),
        source="test",
        received_at=datetime.now(timezone.utc),
    )
    result = service.evaluate_market_snapshot(snapshot)
    first = service.record_market_analysis(result, market_timestamp=snapshot.candles[-1].timestamp)
    second = service.record_market_analysis(result, market_timestamp=snapshot.candles[-1].timestamp)
    assert first is not None
    assert second is None
    assert len(service.memory_view()) == 1
