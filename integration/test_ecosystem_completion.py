from integration.ecosystem_service import EcosystemService
from core.operation_lineage import OperationLineage
from core.operational_runtime import build_operational_runtime


def test_outcome_updates_only_selected_record():
    service = EcosystemService()
    record = service.analyze({"score": 85, "confirmed": True, "filters_ok": True, "symbol": "EURUSD", "timeframe": "5m"})
    updated = service.record_outcome(record.decision_id, "WIN")
    assert updated.outcome == "WIN"
    assert updated.signal == record.signal
    assert service.statistics()["wins"] == 1


def test_replay_rejects_non_object_case():
    service = EcosystemService()
    try:
        service.replay(["bad"])
    except ValueError as exc:
        assert "objeto" in str(exc)
    else:
        raise AssertionError("replay should reject non-object cases")


def test_fail_closed_status_boundaries():
    service = EcosystemService()
    assert service.risk_status()["allowed"] is False
    assert service.news_status()["live"] is False
    assert service.connections()["real"] == "DESABILITADO"


def test_manual_outcome_is_blocked_when_decision_has_operational_lineage(tmp_path):
    runtime = build_operational_runtime(tmp_path)
    service = EcosystemService(operational_runtime=runtime)
    record = service.analyze({"score": 85, "confirmed": True, "filters_ok": True, "symbol": "EURUSD", "timeframe": "5m"})
    runtime.lineage.put(OperationLineage(record.decision_id, "cycle-x", "request-x"))
    operational = record.with_outcome("OPEN")
    service.memory[0] = operational
    try:
        service.record_outcome(record.decision_id, "WIN")
    except ValueError as exc:
        assert "reconciliação externa" in str(exc)
    else:
        raise AssertionError("manual operational outcome should be blocked")



def test_market_analysis_uses_the_same_cycle_and_candle_claim_as_automatic_runtime(tmp_path):
    from datetime import datetime, timedelta, timezone
    from core.p122_broker_market_data import BrokerMarketDataSnapshot
    from data.models import Candle

    runtime = build_operational_runtime(tmp_path)
    service = EcosystemService(operational_runtime=runtime)
    base = datetime(2026, 9, 29, 1, 0, tzinfo=timezone.utc)
    candles = tuple(
        Candle(
            timestamp=base + timedelta(minutes=5 * index),
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
            volume=1000.0,
        )
        for index in range(20)
    )
    snapshot = BrokerMarketDataSnapshot(
        symbol="EURUSD",
        timeframe="5m",
        candles=candles,
        source="test",
        received_at=base + timedelta(minutes=100),
    )
    runtime.market_data.update(snapshot, now=snapshot.received_at, expected_interval_seconds=300)

    record = service.analyze_market(symbol="EURUSD", timeframe="5m")

    assert record.cycle_id
    assert record.market_timestamp == candles[-1].timestamp.isoformat()
    assert runtime.daily_journal.has_market_decision(
        symbol="EURUSD", timeframe="5m", market_timestamp=record.market_timestamp
    ) is True



def test_selected_market_analysis_callback_is_present_and_cleans_transient_candidates(tmp_path):
    from datetime import datetime, timedelta, timezone
    from core.p122_broker_market_data import BrokerMarketDataSnapshot
    from data.models import Candle

    runtime = build_operational_runtime(tmp_path)
    service = EcosystemService(operational_runtime=runtime)
    assert callable(service.handle_selected_market_analysis)

    base = datetime(2026, 9, 29, 2, 0, tzinfo=timezone.utc)
    candles = tuple(
        Candle(
            timestamp=base + timedelta(minutes=5 * index),
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
            volume=1000.0,
        )
        for index in range(20)
    )
    snapshot = BrokerMarketDataSnapshot(
        symbol="EURUSD",
        timeframe="5m",
        candles=candles,
        source="test",
        received_at=base,
    )
    service._senior_cycles_by_decision["pending:GBPUSD:5m:old"] = object()
    result = service.evaluate_market_snapshot(snapshot)
    record = service.handle_selected_market_analysis(snapshot, result)

    assert record is not None
    assert record.cycle_id
    assert "pending:GBPUSD:5m:old" not in service._senior_cycles_by_decision
    assert record.decision_id in service._senior_cycles_by_decision
