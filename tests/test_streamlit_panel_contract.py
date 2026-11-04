import json
from pathlib import Path


PANEL_DIR = Path(__file__).resolve().parents[1] / "streamlit_panel"


def test_streamlit_panel_keeps_the_four_reference_navigation_areas():
    config = json.loads((PANEL_DIR / "controlador_trader_referencia_visual.json").read_text(encoding="utf-8"))
    assert list(config["open_state"]["tabs"]) == ["COCKPIT", "ANÁLISE", "ESTUDO", "MAIS / ADMIN"]
    assert config["open_state"]["tabs"]["MAIS / ADMIN"][0] == "Financeiro"
    assert config["closed_state"]["trigger"] == "C"


def test_streamlit_panel_connects_assistant_and_fiscal_to_existing_api():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    for route in (
        "/api/assistant/conversations",
        "/api/assistant/history",
        "/api/assistant/chat",
        "/api/fiscal-reserve",
        "/api/fiscal-reserve/pending",
        "/api/fiscal-reserve/results",
    ):
        assert route in source
    assert "CONTROLADOR_TRUSTED_IDENTITY_HEADER" in source
    assert "REAL permanece bloqueado" in source or "REAL" in source



def test_streamlit_fiscal_panel_records_losses_and_pages_the_ledger():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert "min_value=-1000000000000.0" in source
    assert "fiscal_history_offset" in source
    assert "fiscal_history_next" in source
    assert "fiscal_history_previous" in source
    assert "compensação ou transporte de perdas não é calculado automaticamente" in source


def test_streamlit_mt5_preview_requires_explicit_classification_and_confirmation():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert '"/api/fiscal-reserve/mt5-confirm"' in source
    assert '"confirmed": True' in source
    assert "mercado brasileiro elegível" in source
    assert 'account_currency == "BRL"' in source
    assert '"/api/fiscal-reserve/mt5-pending-result"' in source
    assert "Guardar como pendência" in source


def test_streamlit_panel_preserves_signed_foreign_results_as_pending():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert '"/api/fiscal-reserve/pending-result"' in source
    assert '"original_result": amount_signed' in source
    assert "PENDENTE DE CLASSIFICAÇÃO" in source
    assert "Resultado original (+ lucro / - prejuízo)" in source


def test_streamlit_mt5_foreign_result_can_only_be_saved_as_pending():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert '"/api/fiscal-reserve/mt5-pending-result"' in source
    assert '"confirmed": True' in source
    assert "Guardar como pendência" in source
    assert "sem classificação ou cálculo" in source



def test_streamlit_fiscal_panel_shows_foreign_pending_counts_by_period_without_amounts():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert 'summary.get("foreign_pending", {})' in source
    assert 'pending_periods.get(period, {})' in source
    assert "Exterior pendente · {label}" in source
    assert "sem cálculo" in source



def test_streamlit_mt5_preview_displays_opening_and_closing_timestamps():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert '"Abertura UTC": item.get("opened_at_utc")' in source
    assert '"Encerramento UTC": item.get("occurred_at_utc")' in source



def test_streamlit_does_not_show_unavailable_foreign_pending_counts_as_zero():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert 'foreign_pending.get("available") is False' in source
    assert "A contagem das pendências do exterior está indisponível" in source



def test_streamlit_mt5_day_trade_requires_brazilian_market_scope_confirmation():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert "mercado brasileiro elegível" in source
    assert '"market_scope": "BR_ELIGIBLE_MARKET"' in source


def test_streamlit_panel_explains_fiscal_catalog_automation_boundaries():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert "Categorias fiscais e estado da automação" in source
    assert "Pendente · sem cálculo automático" in source
    assert "Lançamento parcial habilitado" in source
    assert "Nenhuma categoria adicional foi habilitada" in source

def test_streamlit_fiscal_catalog_reuses_the_single_summary_request():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert source.count('api("/api/fiscal-reserve?limit=50&offset="') == 1
    assert 'api("/api/fiscal-reserve")' not in source
