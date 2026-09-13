from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.candle_analysis_evaluator import evaluate_candle_snapshot
from core.p122_broker_market_data import BrokerMarketDataBoundary
from execution.icmarkets_mt5_market_data import ICMarketsMT5DemoMarketDataAdapter
from execution.mt5_asset_selector import rank_mt5_assets
from execution.mt5_instrument_universe import discover_mt5_instruments
from integration.mt5_market_analysis_bridge import analyze_mt5_candidates_from_market_data
from integration.mt5_multi_asset_analysis import MT5AssetAnalysis


def build_ic_markets_mt5_demo_analysis_service(*, mt5_module: Any = None, timeframe: str = "5m", candle_limit: int = 50, analysis_limit: int | None = None, evaluator: Callable | None = None) -> Callable[[], tuple[MT5AssetAnalysis, ...]]:
    if not isinstance(timeframe, str) or not timeframe.strip():
        raise ValueError("timeframe inválido")
    if not isinstance(candle_limit, int) or isinstance(candle_limit, bool) or candle_limit <= 0:
        raise ValueError("candle_limit inválido")
    if analysis_limit is not None and (not isinstance(analysis_limit, int) or isinstance(analysis_limit, bool) or analysis_limit < 0):
        raise ValueError("analysis_limit inválido")
    if evaluator is not None and not callable(evaluator):
        raise TypeError("evaluator deve ser chamável")
    selected_evaluator = evaluator or evaluate_candle_snapshot

    def analyze() -> tuple[MT5AssetAnalysis, ...]:
        runtime = mt5_module
        if runtime is None:
            try:
                import MetaTrader5 as runtime_module  # type: ignore
            except ImportError as exc:
                raise RuntimeError("MetaTrader5 não instalado; análise DEMO indisponível.") from exc
            runtime = runtime_module
        statuses = discover_mt5_instruments(runtime)
        candidates = rank_mt5_assets(statuses, limit=analysis_limit)
        adapter = ICMarketsMT5DemoMarketDataAdapter(mt5_module=runtime)
        boundary = BrokerMarketDataBoundary(adapter, source="IC Markets MT5 DEMO")
        return analyze_mt5_candidates_from_market_data(candidates, boundary, timeframe=timeframe, limit=candle_limit, evaluator=selected_evaluator, analysis_limit=analysis_limit)

    return analyze
