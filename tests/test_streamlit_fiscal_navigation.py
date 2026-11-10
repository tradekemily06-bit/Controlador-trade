from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "streamlit_panel"


def test_fiscal_reserve_and_ecosystem_assistant_have_dedicated_streamlit_areas():
    source = (PANEL / "app.py").read_text(encoding="utf-8")
    readme = (PANEL / "README.md").read_text(encoding="utf-8")

    # Preserve the supplied Figma reference JSON, but allow the active
    # Streamlit product to give cross-cutting modules their own destinations.
    assert 'AREAS["RESERVA FISCAL"] = ["Reserva Fiscal"]' in source
    assert 'AREAS["ASSISTENTE DO ECOSSISTEMA"] = ["Assistente do Ecossistema"]' in source
    assert 'if module == "Reserva Fiscal":' in source
    assert 'elif module == "Assistente do Ecossistema":' in source
    assert "show_fiscal()" in source
    assert "show_assistant()" in source
    assert 'AREAS["MAIS / ADMIN"] = list(_REFERENCE_TABS["MAIS / ADMIN"])' in source
    assert "show_finance_overview()" in source
    assert "Visão geral financeira do Ecossistema." in source
    assert 'if module_name == "Financeiro":' in source
    assert "show_finance_overview()" in source
    assert "**Reserva Fiscal** possui uma área principal própria" in readme
    assert "**Assistente do Ecossistema** possui uma área principal própria" in readme


def test_mt5_demo_cockpit_navigation_name_distinguishes_connection_from_simulator():
    source = (PANEL / "app.py").read_text(encoding="utf-8")
    readme = (PANEL / "README.md").read_text(encoding="utf-8")

    assert '"Ambiente MT5 DEMO": ("Conexões e ambiente", "/api/connections")' in source
    assert 'if module_name == "Ambiente MT5 DEMO":' in source
    assert "Replay** e **Simulador** permanecem em ESTUDO" in readme


def test_streamlit_labels_default_and_user_configured_planning_rates_separately():
    source = (PANEL / "app.py").read_text(encoding="utf-8")
    assert '"DEFAULT": "padrão inicial do sistema"' in source
    assert '"USER_CONFIGURED": "configurado pelo usuário"' in source
    assert '"LEGACY_UNKNOWN": "origem anterior não identificada"' in source
