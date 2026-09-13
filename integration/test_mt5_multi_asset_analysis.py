from core.models import AnalysisResult, Signal
from execution.mt5_asset_selector import MT5AssetCandidate
from integration.mt5_multi_asset_analysis import analyze_ranked_mt5_assets


def _candidate(symbol: str, rank: int) -> MT5AssetCandidate:
    return MT5AssetCandidate(symbol=symbol, asset_class="crypto", weekend_capable=True, rank=rank)


def test_analyzes_all_candidates_and_prioritizes_actionable_results():
    candidates = (_candidate("ADAUSD", 1), _candidate("SOLUSD", 2), _candidate("LTCUSD", 3))
    def analyzer(symbol: str) -> AnalysisResult:
        if symbol == "ADAUSD": return AnalysisResult(Signal.AGUARDAR, 60, "aguardar", False, symbol=symbol)
        if symbol == "SOLUSD": return AnalysisResult(Signal.COMPRA, 88, "compra", True, symbol=symbol)
        return AnalysisResult(Signal.VENDA, 18, "venda", True, symbol=symbol)
    result = analyze_ranked_mt5_assets(candidates, analyzer)
    assert [item.result.signal for item in result] == [Signal.COMPRA, Signal.VENDA, Signal.AGUARDAR]
    assert [item.result.symbol for item in result] == ["SOLUSD", "LTCUSD", "ADAUSD"]


def test_fills_missing_symbol_without_changing_analysis():
    result = analyze_ranked_mt5_assets((_candidate("BTCUSD", 1),), lambda symbol: AnalysisResult(Signal.AGUARDAR, 50, "sem confirmação", False))
    assert result[0].result.symbol == "BTCUSD"
    assert result[0].result.score == 50


def test_limit_applies_before_analysis():
    seen = []
    result = analyze_ranked_mt5_assets((_candidate("ADAUSD", 1), _candidate("SOLUSD", 2)), lambda symbol: (seen.append(symbol) or AnalysisResult(Signal.AGUARDAR, 50, "aguardar", False, symbol=symbol)), limit=1)
    assert len(result) == 1
    assert seen == ["ADAUSD"]


def test_invalid_analyzer_result_is_rejected():
    try:
        analyze_ranked_mt5_assets((_candidate("ETHUSD", 1),), lambda symbol: "invalid")
    except TypeError as exc:
        assert "AnalysisResult" in str(exc)
    else:
        raise AssertionError("expected TypeError")
