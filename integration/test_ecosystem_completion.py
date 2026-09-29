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


def test_market_data_runtime_retries_selected_callback_after_failure():
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    from core.market_data_runtime_state import MarketDataRuntimeState
    from core.market_data_runtime_integrity import MarketDataRuntimeIntegrity
    from core.p122_broker_market_data import BrokerMarketDataBoundary
    from data.models import Candle
    from integration.persistent_market_data_runtime import MarketDataRuntimeConfig, PersistentMarketDataRuntime

    base = datetime(2026, 9, 29, 3, 0, tzinfo=timezone.utc)
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

    class Provider:
        def fetch_market_data(self, request):
            return candles

    boundary = BrokerMarketDataBoundary(Provider(), "test")
    state = MarketDataRuntimeState(MarketDataRuntimeIntegrity())
    calls = []

    def handler(snapshot, result):
        calls.append(snapshot.symbol)
        if len(calls) == 1:
            raise RuntimeError("temporary callback failure")

    runtime = PersistentMarketDataRuntime(
        boundary,
        state,
        MarketDataRuntimeConfig(symbol="EURUSD", timeframe="5m", limit=20, poll_seconds=5),
        candidate_selector=lambda: ("EURUSD",),
        candidate_analyzer=lambda snapshot: SimpleNamespace(
            signal=SimpleNamespace(value="COMPRA"), confirmed=True, score=90.0
        ),
        selected_result_handler=handler,
    )

    runtime._run_candidate_sweep()
    assert calls == ["EURUSD"]
    assert runtime._last_processed_candle_key is None

    runtime._run_candidate_sweep()
    assert calls == ["EURUSD", "EURUSD"]
    assert runtime._last_processed_candle_key == ("EURUSD", "5m", candles[-1].timestamp.isoformat())

def test_market_analysis_releases_exact_claim_when_decision_persistence_fails(tmp_path):
    from datetime import datetime, timedelta, timezone
    from core.p122_broker_market_data import BrokerMarketDataSnapshot
    from data.models import Candle

    runtime = build_operational_runtime(tmp_path)
    service = EcosystemService(operational_runtime=runtime)
    service.store.save = lambda record: False

    base = datetime(2026, 9, 29, 4, 0, tzinfo=timezone.utc)
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
    result = service.evaluate_market_snapshot(snapshot)
    record = service.record_market_analysis(result, market_timestamp=candles[-1].timestamp)

    assert record is None
    assert runtime.daily_journal.has_market_decision(
        symbol="EURUSD",
        timeframe="5m",
        market_timestamp=candles[-1].timestamp.isoformat(),
    ) is False
    assert not service._senior_cycles_by_decision


def test_manual_study_outcome_does_not_enter_operational_journal(tmp_path):
    runtime = build_operational_runtime(tmp_path)
    service = EcosystemService(operational_runtime=runtime)
    record = service.analyze({
        "score": 85,
        "confirmed": True,
        "filters_ok": True,
        "symbol": "EURUSD",
        "timeframe": "5m",
    })

    service.record_outcome(record.decision_id, "WIN")

    assert service.statistics()["wins"] == 1
    assert runtime.daily_journal.entries() == ()
def test_demo_execution_blocks_when_persisted_recovery_requires_reconciliation(tmp_path):
    from dataclasses import replace
    from datetime import datetime, timezone
    from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState

    runtime = build_operational_runtime(tmp_path)
    service = EcosystemService(operational_runtime=runtime)
    record = service.analyze({
        "score": 85,
        "confirmed": True,
        "filters_ok": True,
        "symbol": "EURUSD",
        "timeframe": "5m",
    })
    service.memory[0] = replace(
        record,
        market_timestamp=datetime(2026, 9, 29, 5, 0, tzinfo=timezone.utc).isoformat(),
    )
    runtime.execution_lifecycle.put(
        ExecutionLifecycleRecord(
            "unrelated-pending",
            ExecutionLifecycleState.PENDING,
            datetime.now(timezone.utc),
        )
    )

    result = service.execute_demo(
        symbol="EURUSD",
        signal=record.signal,
        amount=1,
        duration_seconds=60,
        decision_id=record.decision_id,
    )

    assert result["accepted"] is False
    assert result["status"] == "BLOCKED_RECOVERY"
    assert result["recovery_state"] == "REQUIRES_RECONCILIATION"


def test_partial_external_result_remains_reconcilable_until_final_outcome(tmp_path):
    from types import SimpleNamespace

    runtime = build_operational_runtime(tmp_path)
    record = EcosystemService(operational_runtime=runtime).analyze({
        "score": 85,
        "confirmed": True,
        "filters_ok": True,
        "symbol": "EURUSD",
        "timeframe": "5m",
    })

    calls = []

    class Observer:
        def observe_closed_position(self, request_id):
            calls.append(request_id)
            return None

    service = EcosystemService(
        operational_runtime=runtime,
        outcome_observer=Observer(),
    )
    service.memory.append(record)
    runtime.lineage.put(
        OperationLineage(
            record.decision_id,
            "cycle-partial",
            "request-partial",
            external_id="1001",
            external_container_id="2001",
            external_close_id="3001",
            external_close_ids=("3001",),
            external_result_ids=("3001",),
        )
    )

    result = service.reconcile_pending_outcomes()

    assert calls == ["request-partial"]
    assert result[0]["observed"] is False
