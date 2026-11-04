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
        "/api/assistant/status",
        "/api/assistant/chat",
        "/api/fiscal-reserve",
        "/api/fiscal-reserve/pending",
        "/api/fiscal-reserve/results",
    ):
        assert route in source
    assert "/api/assistant/conversations" not in source
    assert "/api/assistant/history" not in source
    assert "CONTROLADOR_TRUSTED_IDENTITY_HEADER" in source
    assert "REAL permanece bloqueado" in source or "REAL" in source



def test_streamlit_fiscal_panel_records_losses_and_pages_the_ledger():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert "min_value=-1000000000000.0" in source
    assert "fiscal_history_offset" in source
    assert "fiscal_history_next" in source
    assert "fiscal_history_previous" in source
    assert "Compensações mensais e créditos de IRRF não são calculados." in source


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

def test_streamlit_keeps_brazilian_pending_items_separate_from_foreign_queue():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert "/api/fiscal-reserve/domestic-pending" in source
    assert "/api/fiscal-reserve/domestic-pending/summary" in source
    assert "Brasil · pendente de classificação" in source
    assert "Exterior · pendente de classificação" in source
    assert "Fila brasileira indisponível" in source


def test_streamlit_domestic_pending_can_distinguish_zero_from_missing_result():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert 'domestic_has_result = st.checkbox("Informar resultado realizado em R$ (inclusive zero)"' in source
    assert "if domestic_has_result:" in source
    assert 'domestic_payload["realized_result_brl"] = domestic_result' in source


def test_streamlit_documents_missing_reference_images_outside_the_panel():
    readme = (PANEL_DIR / "README.md").read_text(encoding="utf-8")
    assert "O Figma é somente referência visual" in readme
    assert "não estão presentes neste branch" in readme
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert "não é a reprodução visual aprovada do Figma" not in source
    assert "As cinco imagens originais" not in source


def test_streamlit_marks_mt5_tax_classification_as_user_declared_pending_review():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert "DECLARAÇÃO DO USUÁRIO · REVISÃO PENDENTE" in source
    assert 'evidence.get("tax_classification_status") == "USER_DECLARED_PENDING_REVIEW"' in source
    assert "fila brasileira separada, sem cálculo e fora dos totais" in source


def test_streamlit_unverified_mt5_history_never_displays_reserve_rate_or_amount():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert 'if not user_declared_pending:' in source
    assert "Percentual de planejamento (%)" in source
    assert "Reserva estimada (R$)" in source
    assert "fila brasileira separada, sem cálculo e fora dos totais" in source


def test_streamlit_labels_user_declared_day_trade_planning_estimates():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert "PLANEJAMENTO · DECLARAÇÃO DO USUÁRIO" in source
    assert 'evidence.get("tax_classification_status") == "USER_DECLARED_PLANNING_ONLY"' in source
    assert "Confirmo que foi o mesmo ativo, pela mesma instituição, no mesmo dia e em mercado brasileiro elegível." in source


def test_streamlit_brazilian_pending_queue_supports_auditable_professional_review():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert "/api/fiscal-reserve/domestic-pending/" in source
    assert '"/reviews"' in source
    assert "Revisão documental · Brasil" in source
    assert "O sistema não verifica identidade ou registro profissional" in source
    assert "A operação continua pendente, sem cálculo ou inclusão nos totais." in source


def test_streamlit_assistant_displays_provider_readiness_without_exposing_credentials():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert 'api("/api/assistant/status")' in source
    assert "Assistente indisponível:" in source
    assert "Credenciais configuradas; conexão com a API ainda não testada." in source


def test_streamlit_disables_assistant_chat_when_provider_is_unavailable():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert "assistant_available = False" in source
    assert "assistant_available = readiness.get(\"available\") is True" in source
    assert "disabled=not assistant_available" in source


def test_streamlit_foreign_pending_forms_capture_structured_evidence_and_display_it():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    for field in (
        "tax_residency_at_event",
        "income_nature",
        "event_type",
        "fx_conversion_method",
    ):
        assert field in source
    assert "Residência fiscal declarada na data" in source
    assert "Natureza do rendimento / valor" in source
    assert "Tipo de evento" in source
    assert "Método de conversão cambial" in source
    assert "Residência declarada" in source
    assert "Método cambial" in source
    assert "NOT_INFORMED" in source


def test_streamlit_fiscal_summary_labels_accumulated_amount_as_planning_estimate():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert 'c.metric("Estimativa acumulada · Brasil"' in source
    assert "percentual de planejamento configurado" in source
    assert "ESTIMATIVA DE PLANEJAMENTO — não é imposto apurado ou devido." in source
    assert 'summary.get("reserve_semantics", {})' in source


def test_streamlit_assistant_distinguishes_configured_credentials_from_tested_connection():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert 'readiness.get("message")' in source
    assert "Credenciais configuradas; conexão com a API ainda não testada." in source
    assert "disabled=not assistant_available" in source


def test_streamlit_foreign_pending_queue_exposes_auditable_professional_review():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert 'foreign_pending_data = api(f"/api/fiscal-reserve/pending?limit=50&offset={foreign_offset}")' in source
    assert "foreign_pending_next" in source
    assert "foreign_pending_previous" in source
    assert '"/api/fiscal-reserve/pending/"' in source
    assert "Revisão documental · Exterior" in source
    assert "FOREIGN_FINANCIAL_INVESTMENT" in source
    assert "FOREIGN_ENTITY_CONTROLLED" in source
    assert "FOREIGN_CRYPTO" in source
    assert "Identidade" in source
    assert "NÃO VERIFICADA" in source
    assert "A operação continua pendente, sem cálculo ou inclusão nos totais." in source



def test_streamlit_assistant_does_not_expose_past_conversation_history():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert "Nova consulta" in source
    assert "assistant_history" in source
    assert 'api("/api/assistant/conversations")' not in source
    assert 'api("/api/assistant/history?' not in source
    assert 'st.selectbox("Histórico"' not in source
    assert "Excluir conversa e mensagens locais" not in source


def test_streamlit_layout_uses_full_width_and_wraps_responsively():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert ".block-container { width: 100%; max-width: none;" in source
    assert "[role=\"radiogroup\"] { flex-wrap: wrap; }" in source
    assert "@media (max-width: 720px)" in source



def test_streamlit_uses_the_same_fixed_c_toggle_in_open_and_closed_states():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert 'st.container(key="panel-toggle")' in source
    assert 'st.button("C", key="open_control_hub")' in source
    assert 'st.button("C", key="close_control_hub")' in source
    assert ".st-key-panel-toggle { position: fixed;" in source
    assert "border-radius: 50%" in source
    assert 'st.caption("INDISPONÍVEL")' in source


def test_streamlit_closed_panel_contains_only_c_and_unavailable_status():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    start = source.index("if not st.session_state.panel_open:")
    end = source.index("st.stop()", start) + len("st.stop()")
    closed_state = source[start:end]
    assert 'st.button("C", key="open_control_hub")' in closed_state
    assert 'st.caption("INDISPONÍVEL")' in closed_state
    assert "Controlador-Trader" not in closed_state
    assert "Histórico" not in closed_state



def test_streamlit_does_not_fill_unimplemented_modules_with_placeholder_copy():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert 'st.info(f"Módulo {module} selecionado.' not in source
    assert "A integração funcional deste módulo ainda não foi habilitada nesta prévia." not in source


def test_streamlit_leverage_control_is_an_enabled_toggle_without_status_copy():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert 'st.checkbox("Alavancagem", value=False, key="leverage_enabled")' in source
    assert "Desativada" not in source



def test_assistant_is_a_standalone_module_inside_streamlit_without_changing_figma_tabs():
    config = json.loads((PANEL_DIR / "controlador_trader_referencia_visual.json").read_text(encoding="utf-8"))
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert list(config["open_state"]["tabs"]) == ["COCKPIT", "ANÁLISE", "ESTUDO", "MAIS / ADMIN"]
    assert 'AREAS["MAIS / ADMIN"].append("Assistente do Ecossistema")' in source
    assert 'if module == "Assistente do Ecossistema":' in source
    assert 'financial = st.radio("Financeiro", ["Reserva Fiscal", "Assistente do Ecossistema"]' not in source
    assert "show_assistant()" in source


def test_streamlit_readme_identifies_the_streamlit_panel_as_user_facing_and_figma_as_reference():
    readme = (PANEL_DIR / "README.md").read_text(encoding="utf-8")
    assert "O Figma é somente referência visual" in readme
    assert "painel de uso pretendido" in readme
    assert "Assistente do Ecossistema é acrescentado como módulo funcional próprio em MAIS / ADMIN" in readme



def test_streamlit_operational_modules_use_live_read_only_runtime_endpoints():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    for route in (
        "/api/health",
        "/api/statistics",
        "/api/risk",
        "/api/notifications",
        "/api/connections",
        "/api/memory?limit=50",
        "/api/learning",
        "/api/onboarding",
        "/api/preferences",
    ):
        assert route in source
    assert "show_readonly_module(module)" in source
    assert "st.empty()" not in source


def test_streamlit_market_analysis_requires_demo_confirmation_and_never_enables_execution():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert 'api("/api/runtime/analysis", "POST"' in source
    assert 'confirmed = st.checkbox("Confirmo que esta análise é somente para estudo em DEMO/SIMULAÇÃO.")' in source
    analysis_screen = source[source.index("def show_market_analysis"):source.index("def show_readonly_module")]
    assert '"confirmed": True' not in analysis_screen
    assert '"filters_ok": True' not in analysis_screen
    assert "preferências de segurança do runtime são respeitadas" in analysis_screen
    assert 'Execução permitida: NÃO' in analysis_screen



def test_streamlit_preferences_never_submit_execution_authority_fields():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    start = source.index('if module_name == "Configurações":')
    end = source.index('if module_name == "Análise de Mercado":', start)
    preferences_screen = source[start:end]
    assert '"real_execution_enabled"' not in preferences_screen
    assert '"autonomous_operation_enabled"' not in preferences_screen
    assert '"selected_mode"' not in preferences_screen
    assert '"execution_allowed"' not in preferences_screen
    assert '"require_closed_candle": require_closed' in preferences_screen
    assert '"require_filters": require_filters' in preferences_screen


def test_streamlit_operational_screens_render_human_readable_summaries_without_raw_json_dump():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert "Central de Notificações" in source
    assert 'data.get("critical_count", 0)' in source
    assert "Limite de perda diária" in source
    assert "Kill Switch" in source
    assert "Fontes externas exigem validação" in source
    assert "Guia de primeiro uso" in source
    assert "Salvar preferências" in source
    assert "Salvar aparência" in source
    assert "Salvar notificações" in source
    assert '"/api/preferences"' in source
    assert '"/api/preferences/candles"' in source
    assert '"/api/preferences/notifications"' in source
    assert "alertas críticos" in source.lower()
    assert "st.json(data)" not in source


def test_streamlit_replay_uses_historical_mt5_demo_data_without_orders():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert 'api("/api/replay/mt5", "POST"' in source
    assert "Reproduzir histórico DEMO" in source
    assert "candles fechados" in source
    assert "Antecipação de candles futuros: NÃO" in source
    assert "Replay concluído sem envio de ordens." in source
    assert 'show_replay()' in source
