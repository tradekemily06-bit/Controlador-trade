from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_streamlit_demo_recovery_lists_positions_and_requires_read_only_reconciliation_before_close():
    panel = (ROOT / "streamlit_panel" / "app.py").read_text(encoding="utf-8")
    branch = panel.split('if module_name == "MT5 DEMO / Simulação":', 1)[1].split(
        'if module_name == "Conexões":', 1
    )[0]

    assert 'api("/api/runtime/positions/recovery")' in branch
    assert 'api("/api/runtime/close/reconcile", "POST"' in branch
    assert 'api("/api/runtime/close", "POST"' in branch
    assert 'state == "BROKER_CONFIRMED_OPEN"' in branch
    assert 'state == "RECONCILIATION_REQUIRED"' in branch
    assert 'st.checkbox("Confirmo que desejo solicitar o fechamento desta posição DEMO específica."' in branch
    assert 'st.form_submit_button("Fechar esta posição DEMO", disabled=not confirmed)' in branch
    assert "Nenhuma posição é fechada automaticamente." in branch


def test_streamlit_demo_recovery_disables_close_when_account_identity_is_unverified():
    panel = (ROOT / "streamlit_panel" / "app.py").read_text(encoding="utf-8")
    branch = panel.split('if module_name == "MT5 DEMO / Simulação":', 1)[1].split(
        'if module_name == "Conexões":', 1
    )[0]

    blocked = branch.split('if state == "BLOCKED_ACCOUNT_IDENTITY":', 1)[1].split(
        'elif state == "BROKER_CONFIRMED_OPEN":', 1
    )[0]
    assert "st.error(" in blocked
    assert 'state == "BROKER_CONFIRMED_OPEN"' in branch


def test_streamlit_mt5_demo_module_displays_timed_exit_status():
    panel = (ROOT / "streamlit_panel" / "app.py").read_text(encoding="utf-8")
    branch = panel.split('if module_name == "MT5 DEMO / Simulação":', 1)[1].split(
        'if module_name == "Conexões":', 1
    )[0]
    assert 'api("/api/runtime/timed-exits")' in branch
    assert "Saídas temporizadas DEMO" in branch
    assert "Horários best-effort" in branch
