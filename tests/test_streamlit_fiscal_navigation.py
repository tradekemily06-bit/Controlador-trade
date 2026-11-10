from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "streamlit_panel"


def test_fiscal_reserve_is_a_dedicated_streamlit_navigation_module():
    source = (PANEL / "app.py").read_text(encoding="utf-8")
    readme = (PANEL / "README.md").read_text(encoding="utf-8")

    assert 'AREAS = {name: list(modules) for name, modules in CONFIG["open_state"]["tabs"].items()}' in source
    assert 'if module == "Financeiro":' in source
    assert 'st.radio("Financeiro", ["Reserva Fiscal", "Assistente do Ecossistema"]' in source
    assert 'def show_fiscal() -> None:' in source
    assert 'def show_assistant() -> None:' in source
    assert 'st.subheader("Reserva Fiscal")' in source
    assert "Reserva Fiscal e Assistente do Ecossistema ficam agrupados dentro de Financeiro" in readme



def test_streamlit_labels_default_and_user_configured_planning_rates_separately():
    source = (PANEL / "app.py").read_text(encoding="utf-8")
    assert '"DEFAULT": "padrão inicial do sistema"' in source
    assert '"USER_CONFIGURED": "configurado pelo usuário"' in source
    assert '"LEGACY_UNKNOWN": "origem anterior não identificada"' in source
