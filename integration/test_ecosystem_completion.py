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
    runtime.lineage.put(OperationLineage("decision-x", "cycle-x", "request-x"))
    operational = record.with_outcome("OPEN")
    service.memory[0] = operational
    try:
        service.record_outcome(record.decision_id, "WIN")
    except ValueError as exc:
        assert "reconciliação externa" in str(exc)
    else:
        raise AssertionError("manual operational outcome should be blocked")
