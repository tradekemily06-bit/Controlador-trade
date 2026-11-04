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
    assert 'Confirmo que este resultado pertence à categoria Brasil · day trade.' in source
    assert 'account_currency == "BRL"' in source
    assert "moeda original, classificação e conversão documentada" in source


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
