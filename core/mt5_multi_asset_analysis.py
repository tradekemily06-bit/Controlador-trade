from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .models import AnalysisResult, Signal
from execution.mt5_asset_selector import MT5AssetCandidate


@dataclass(frozen=True)
class MT5AssetAnalysis:
    """Read-only analysis result for one ranked MT5 asset."""

    candidate: MT5AssetCandidate
    result: AnalysisResult


Analyzer = Callable[[str], AnalysisResult]


def analyze_ranked_mt5_assets(
    candidates: Iterable[MT5AssetCandidate],
    analyzer: Analyzer,
    *,
    limit: int | None = None,
) -> tuple[MT5AssetAnalysis, ...]:
    """Run the existing decision engine across ranked assets without trading.

    The analyzer owns market-data retrieval and technical evaluation. This
    orchestration layer only applies the ranked universe, preserves the
    broker-agnostic signal result, and returns the strongest actionable
    candidates first. It never places, modifies, or closes orders.
    """
    if not callable(analyzer):
        raise TypeError("analyzer deve ser chamável")
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 0):
        raise ValueError("limit deve ser um inteiro não negativo")

    selected = list(candidates)
    if limit is not None:
        selected = selected[:limit]

    analyses: list[MT5AssetAnalysis] = []
    for candidate in selected:
        result = analyzer(candidate.symbol)
        if not isinstance(result, AnalysisResult):
            raise TypeError("analyzer deve retornar AnalysisResult")
        if result.symbol is None:
            result = AnalysisResult(
                signal=result.signal,
                score=result.score,
                reason=result.reason,
                confirmed=result.confirmed,
                symbol=candidate.symbol,
                timeframe=result.timeframe,
            )
        analyses.append(MT5AssetAnalysis(candidate=candidate, result=result))

    def priority(item: MT5AssetAnalysis) -> tuple[int, float, int]:
        signal = item.result.signal
        if signal is Signal.COMPRA:
            strength = float(item.result.score)
        elif signal is Signal.VENDA:
            strength = 100.0 - float(item.result.score)
        else:
            strength = 0.0
        actionable = signal in {Signal.COMPRA, Signal.VENDA}
        return (0 if actionable else 1, -strength, item.candidate.rank)

    return tuple(sorted(analyses, key=priority))
