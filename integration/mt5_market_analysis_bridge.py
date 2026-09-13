from __future__ import annotations

from collections.abc import Callable, Iterable

from core.models import AnalysisResult
from core.p122_broker_market_data import BrokerMarketDataBoundary, BrokerMarketDataRequest, BrokerMarketDataSnapshot
from execution.mt5_asset_selector import MT5AssetCandidate
from integration.mt5_multi_asset_analysis import MT5AssetAnalysis, analyze_ranked_mt5_assets

SnapshotEvaluator = Callable[[BrokerMarketDataSnapshot], AnalysisResult]


def build_mt5_snapshot_analyzer(boundary: BrokerMarketDataBoundary, *, timeframe: str, limit: int, evaluator: SnapshotEvaluator) -> Callable[[str], AnalysisResult]:
    if not isinstance(boundary, BrokerMarketDataBoundary):
        raise TypeError("boundary deve ser BrokerMarketDataBoundary")
    if not isinstance(timeframe, str) or not timeframe.strip():
        raise ValueError("timeframe inválido")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise ValueError("limit inválido")
    if not callable(evaluator):
        raise TypeError("evaluator deve ser chamável")

    def analyze(symbol: str) -> AnalysisResult:
        snapshot = boundary.fetch(BrokerMarketDataRequest(symbol=symbol, timeframe=timeframe, limit=limit))
        result = evaluator(snapshot)
        if not isinstance(result, AnalysisResult):
            raise TypeError("evaluator deve retornar AnalysisResult")
        if result.symbol is None:
            result.symbol = snapshot.symbol
        if result.timeframe is None:
            result.timeframe = snapshot.timeframe
        return result

    return analyze


def analyze_mt5_candidates_from_market_data(candidates: Iterable[MT5AssetCandidate], boundary: BrokerMarketDataBoundary, *, timeframe: str, limit: int, evaluator: SnapshotEvaluator, analysis_limit: int | None = None) -> tuple[MT5AssetAnalysis, ...]:
    analyzer = build_mt5_snapshot_analyzer(boundary, timeframe=timeframe, limit=limit, evaluator=evaluator)
    return analyze_ranked_mt5_assets(candidates, analyzer, limit=analysis_limit)
