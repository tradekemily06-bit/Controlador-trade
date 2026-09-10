from integration.ecosystem_service import EcosystemService


def test_risk_is_fail_closed_without_operational_state():
    status = EcosystemService().risk_status()
    assert status["allowed"] is False
    assert "indisponível" in status["reason"].lower()


def test_news_boundary_is_explicitly_offline():
    status = EcosystemService().news_status(limit=1)
    assert status == {"provider": "UNCONFIGURED", "live": False, "items": []}


def test_real_and_mt5_boundaries_remain_blocked():
    connections = EcosystemService().connections()
    assert connections["real"] == "DESABILITADO"
    assert connections["ic_markets_mt5_demo"] == "VALIDACAO_OPERACIONAL_PENDENTE"
