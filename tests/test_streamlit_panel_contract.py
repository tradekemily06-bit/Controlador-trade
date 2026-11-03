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
