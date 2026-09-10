from integration.ecosystem_service import EcosystemService


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
