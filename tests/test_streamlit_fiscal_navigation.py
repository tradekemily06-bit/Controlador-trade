from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "streamlit_panel"


def test_fiscal_reserve_is_a_dedicated_streamlit_navigation_module():
    source = (PANEL / "app.py").read_text(encoding="utf-8")
    readme = (PANEL / "README.md").read_text(encoding="utf-8")

    assert 'AREAS["MAIS / ADMIN"].append("Reserva Fiscal")' in source
    assert 'elif module in {"Financeiro", "Reserva Fiscal"}:' in source
    assert 'st.subheader("Reserva Fiscal")' in source
    assert "módulo próprio em MAIS / ADMIN" in readme



def test_streamlit_labels_default_and_user_configured_planning_rates_separately():
    source = (PANEL / "app.py").read_text(encoding="utf-8")
    assert '"DEFAULT": "padrão inicial do sistema"' in source
    assert '"USER_CONFIGURED": "configurado pelo usuário"' in source
    assert '"LEGACY_UNKNOWN": "origem anterior não identificada"' in source
