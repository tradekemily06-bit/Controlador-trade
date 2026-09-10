from integration.ecosystem_service import EcosystemService


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
    assert status["mt5_demo"] == "VALIDACAO_OPERACIONAL_PENDENTE"
