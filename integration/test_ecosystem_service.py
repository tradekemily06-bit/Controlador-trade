from datetime import datetime, timedelta, timezone

from integration.ecosystem_service import EcosystemService
from analysis.news_evidence_corroboration import NewsEvidenceCorroborator, NewsSourcePolicy, SQLiteNewsEvidenceStore
from integration.rss_news_provider import NewsItem
import pytest

from core.senior_risk_reasoning import RiskDomain, RiskObservation
from data.models import Candle
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
    assert status["mt5_demo"] == "NOT_CONNECTED"
    assert status["components"]["mt5_demo"] == "NOT_CONNECTED"
    assert status["operational_observability"]["market_data"]["health"] == "NOT_CONNECTED"
    assert status["production_operation_gate"]["authorized"] is False


def test_mt5_demo_is_validated_only_after_healthy_candles_reach_runtime(tmp_path):
    from core.operational_runtime import build_operational_runtime
    from core.p122_broker_market_data import BrokerMarketDataSnapshot

    runtime = build_operational_runtime(tmp_path)
    service = EcosystemService(operational_runtime=runtime)
    assert service.connections()["ic_markets_mt5_demo"] == "NOT_CONNECTED"

    candles = _candles()
    received_at = candles[-1].timestamp + timedelta(minutes=1)
    snapshot = BrokerMarketDataSnapshot(
        symbol="EURUSD",
        timeframe="1m",
        candles=candles,
        source="IC Markets MT5 DEMO",
        received_at=received_at,
    )
    service.update_market_data_snapshot(
        snapshot,
        now=received_at,
        expected_interval_seconds=60,
    )

    assert service.connections()["ic_markets_mt5_demo"] == "DEMO_VALIDADO"
    status = service.system_status()
    assert status["mt5_demo"] == "DEMO_VALIDADO"
    assert status["execution_allowed"] is False
    assert status["real"] == "DESABILITADO"


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



def test_news_status_wires_persistent_source_aware_evidence(tmp_path):
    class FakeNewsProvider:
        def status(self):
            return {"configured": True, "live": True, "feed_count": 2}

        def latest(self, *, symbol=None, limit=10):
            published = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
            return [
                NewsItem(
                    "Federal Reserve announces interest rate decision",
                    "untrusted label one",
                    published,
                    "https://www.reuters.com/markets/fed",
                ),
                NewsItem(
                    "Federal Reserve announces interest rate decision",
                    "untrusted label two",
                    published,
                    "https://www.apnews.com/article/fed",
                ),
            ][:limit]

    store = SQLiteNewsEvidenceStore(
        tmp_path / "news.sqlite3",
        tenant_id="tenant-a",
        subject_id="owner-a",
    )
    store.initialize_schema()
    corroborator = NewsEvidenceCorroborator({
        "www.reuters.com": NewsSourcePolicy(
            "www.reuters.com", "TRUSTED_MEDIA", ("reuters.com",)
        ),
        "www.apnews.com": NewsSourcePolicy(
            "www.apnews.com", "TRUSTED_MEDIA", ("apnews.com",)
        ),
    }, store=store)
    service = EcosystemService(
        news_provider=FakeNewsProvider(),
        news_evidence_correlator=corroborator,
    )

    result = service.news_status(limit=10)

    assert result["live"] is True
    assert result["evidence_processing"]["status"] == "CONNECTED"
    assert result["evidence_processing"]["processed"] == 2
    assert result["evidence_processing"]["records"][1]["corroboration_status"] == "MULTI_SOURCE_CANDIDATE"
    assert result["evidence_processing"]["records"][1]["fact_status"] == "UNVERIFIED_REPORT"
    assert result["evidence_processing"]["fact_confirmation"] == "NEVER_AUTOMATIC"
    assert len(store.load()) == 2


def test_news_status_reports_evidence_not_configured_without_correlator():
    class FakeNewsProvider:
        def status(self):
            return {"configured": True, "live": False}

        def latest(self, *, symbol=None, limit=10):
            return [NewsItem("A headline", "Wire", None, "https://www.reuters.com/story")]

    result = EcosystemService(news_provider=FakeNewsProvider()).news_status()

    assert result["evidence_processing"]["status"] == "NOT_CONFIGURED"
    assert result["evidence_processing"]["processed"] == 0
    assert result["items"][0]["title"] == "A headline"


def test_news_status_keeps_unconfigured_source_out_of_corroboration(tmp_path):
    class FakeNewsProvider:
        def status(self):
            return {"configured": True, "live": True}

        def latest(self, *, symbol=None, limit=10):
            return [NewsItem(
                "Federal Reserve announces interest rate decision",
                "untrusted label",
                "2026-11-28T11:55:00Z",
                "https://unknown.example/story",
            )]

    store = SQLiteNewsEvidenceStore(
        tmp_path / "news.sqlite3",
        tenant_id="tenant-a",
        subject_id="owner-a",
    )
    store.initialize_schema()
    corroborator = NewsEvidenceCorroborator({
        "www.reuters.com": NewsSourcePolicy(
            "www.reuters.com", "TRUSTED_MEDIA", ("reuters.com",)
        ),
    }, store=store)
    result = EcosystemService(
        news_provider=FakeNewsProvider(),
        news_evidence_correlator=corroborator,
    ).news_status()

    assert result["evidence_processing"]["status"] == "PARTIAL"
    assert result["evidence_processing"]["errors"] == 1
    assert result["evidence_processing"]["records"] == []
