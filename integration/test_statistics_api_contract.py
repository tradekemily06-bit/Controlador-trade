from analysis.decision_record import DecisionRecord
from integration.ecosystem_service import EcosystemService


def test_statistics_breakdown_contract_matches_dashboard_keys():
    service = EcosystemService()
    service.memory = [
        DecisionRecord(
            decision_id="1",
            created_at="2026-09-11T12:00:00+00:00",
            symbol="EURUSD",
            timeframe="5m",
            signal="COMPRA",
            score=90,
            confirmed=True,
            reason="test",
            outcome="WIN",
        )
    ]

    stats = service.statistics()
    breakdowns = stats["breakdowns"]

    assert breakdowns["by_symbol"]["EURUSD"]["wins"] == 1
    assert breakdowns["by_timeframe"]["5m"]["wins"] == 1
    assert breakdowns["by_signal"]["COMPRA"]["wins"] == 1
    assert breakdowns["by_score_band"]["85-100"]["wins"] == 1
