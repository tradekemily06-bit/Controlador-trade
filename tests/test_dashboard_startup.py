from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "web" / "index.html"


def test_dashboard_declares_utf8_and_keeps_portuguese_text_intact():
    source = DASHBOARD.read_text(encoding="utf-8")
    assert '<meta charset="utf-8">' in source
    assert "Ecossistema de análise, decisão, risco, memória e execução" in source
    assert "Conexão MT5" in source
    assert "Execução REAL" in source


def test_dashboard_renders_runtime_health_before_waiting_for_risk_gate():
    source = DASHBOARD.read_text(encoding="utf-8")
    status_request = "s=await getJson('/api/status');renderRuntime(s,null)"
    risk_request = "risk=await getJson('/api/risk');renderRuntime(s,risk)"
    assert status_request in source
    assert risk_request in source
    assert source.index(status_request) < source.index(risk_request)


def test_dashboard_loads_market_assets_and_chart_on_initial_page_load():
    source = DASHBOARD.read_text(encoding="utf-8")
    assert "refreshMarketAssets().catch(()=>{});" in source
    assert "refreshMarketChart().catch(()=>{});" in source
