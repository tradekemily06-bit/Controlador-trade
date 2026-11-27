from __future__ import annotations

from datetime import datetime

from analysis.tenant_signal_evidence_store import TenantSignalEvidenceStore
from core.unified_intelligence import UnifiedIntelligence
from data.models import Candle
from data.timeframes import get_timeframe_interval
from integration.standalone_market_analysis import StandaloneMarketAnalysisService
from security.tenant_context import TenantContext


class Provider:
    def __init__(self, timeframe="1m"):
        interval = get_timeframe_interval(timeframe)
        now = datetime.now().astimezone()
        last_open = now - interval
        self.candles = []
        for index in range(12):
            at = last_open - interval * (11 - index)
            price = 1.1 + index * 0.0001
            self.candles.append(Candle(
                timestamp=at, open=price, high=price + 0.0003,
                low=price - 0.0002, close=price + 0.0001, volume=100 + index,
            ))

    def fetch(self, request):
        return tuple(self.candles[-request.limit:])


def test_analyzer_persists_real_market_signal_with_trusted_tenant_context(tmp_path):
    store = TenantSignalEvidenceStore(tmp_path / "signal-evidence.sqlite3")
    owner = TenantContext("tenant-a", "subject-a")
    service = StandaloneMarketAnalysisService(
        provider=Provider(),
        source="mt5:account-demo-1",
        intelligence=UnifiedIntelligence(),
        signal_evidence_sink=store.record_signal,
        market_data_provenance="REAL_MARKET_DATA",
    )
    result = service.analyze(
        symbol="EURUSD", timeframe="M1", limit=12, decision_context=owner
    )
    audit = result["signal_evidence_audit"]
    assert audit["status"] == "RECORDED"
    assert audit["timeframe"] == "1m"
    assert audit["score_type"] == "EVIDENCE_STRENGTH"
    assert audit["probability_of_profit"] is None
    rows = store.list_signals(owner, symbol="EURUSD", timeframe="M1")
    assert len(rows) == 1
    assert rows[0]["direction"] == result["signal"]
    assert rows[0]["evidence_score"] == result["score"]
    assert rows[0]["score_semantics"] == "EVIDENCE_STRENGTH_NOT_WIN_PROBABILITY"


def test_analyzer_does_not_persist_without_explicit_real_data_provenance(tmp_path):
    store = TenantSignalEvidenceStore(tmp_path / "signal-evidence.sqlite3")
    owner = TenantContext("tenant-a", "subject-a")
    service = StandaloneMarketAnalysisService(
        provider=Provider(),
        source="unknown-test-feed",
        intelligence=UnifiedIntelligence(),
        signal_evidence_sink=store.record_signal,
    )
    result = service.analyze(
        symbol="EURUSD", timeframe="M1", limit=12, decision_context=owner
    )
    assert result["signal_evidence_audit"]["status"] == "NOT_CONFIGURED"
    assert store.list_signals(owner) == []


def test_analyzer_does_not_persist_without_tenant_context(tmp_path):
    store = TenantSignalEvidenceStore(tmp_path / "signal-evidence.sqlite3")
    service = StandaloneMarketAnalysisService(
        provider=Provider(),
        source="mt5:account-demo-1",
        intelligence=UnifiedIntelligence(),
        signal_evidence_sink=store.record_signal,
        market_data_provenance="REAL_MARKET_DATA",
    )
    result = service.analyze(symbol="EURUSD", timeframe="M1", limit=12)
    assert result["signal_evidence_audit"]["status"] == "NOT_CONFIGURED"
