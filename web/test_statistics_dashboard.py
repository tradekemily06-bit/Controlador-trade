from pathlib import Path


HTML = Path(__file__).with_name("index.html").read_text(encoding="utf-8")


def test_dashboard_surfaces_periodic_statistics():
    for marker in ("id=\"dailyCount\"", "id=\"weeklyCount\"", "id=\"monthlyCount\""):
        assert marker in HTML


def test_dashboard_surfaces_symbol_and_timeframe_breakdowns():
    assert 'id="symbolBreakdowns"' in HTML
    assert 'id="timeframeBreakdowns"' in HTML
    assert "st.breakdowns?.by_symbol" in HTML
    assert "st.breakdowns?.by_timeframe" in HTML
