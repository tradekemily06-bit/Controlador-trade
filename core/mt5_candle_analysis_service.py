from __future__ import annotations

from collections.abc import Iterable

from .candle_analysis_evaluator import evaluate_candle_snapshot
from .mt5_market_analysis_bridge import analyze_mt5_candidates_from_market_data
from .mt5_multi_asset_analysis import MT5AssetAnalysis
from .p122_broker_market_data import BrokerMarketDataBoundary
from execution.mt5_asset_selector import MT5AssetCandidate


def analyze_mt5_candidates_with_default_candle_method(
    candidates: Iterable[MT5AssetCandidate],
    boundary: BrokerMarketDataBoundary,
    *,
    timeframe: str = "5m",
    limit: int = 50,
    analysis_limit: int | None = None,
) -> tuple[MT5AssetAnalysis, ...]:
    """Run the current conservative candle method across ranked MT5 assets.

    This is a read-only DEMO analysis composition root. It does not place,
    modify, or close orders and does not enable REAL execution.
    """
    return analyze_mt5_candidates_from_market_data(
        candidates,
        boundary,
        timeframe=timeframe,
        limit=limit,
        evaluator=evaluate_candle_snapshot,
        analysis_limit=analysis_limit,
    )
