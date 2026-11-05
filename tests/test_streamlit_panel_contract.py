import ast
import json
from pathlib import Path
from typing import Any


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
    assert "/api/assistant/conversations" in source
    assert "/api/assistant/history?conversation_id=" in source
    assert '"DELETE"' in source
    assert "Conversas anteriores" in source
    assert "Abrir conversa" in source
    assert "Excluir conversa" in source
    assert "histórico local do Assistente no servidor do Ecossistema" in source
    assert "a pergunta, as mensagens recentes desta conversa e um resumo operacional filtrado são enviados pelo servidor à OpenAI." in source
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
    assert "disabled=(not assistant_available) or (not consent_to_openai)" in source


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
    assert "Método declarado" in source
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
    assert "disabled=(not assistant_available) or (not consent_to_openai)" in source


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



def test_streamlit_assistant_exposes_owner_scoped_past_conversation_history():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert "Nova consulta" in source
    assert "assistant_history" in source
    assert 'api("/api/assistant/conversations")' in source
    assert '"/api/assistant/history?conversation_id="' in source
    assert '"/api/assistant/conversations?conversation_id="' in source
    assert '"DELETE"' in source
    assert "Conversas anteriores" in source
    assert "Abrir conversa" in source
    assert "Excluir conversa" in source
    assert "urllib.parse.quote(selected_saved_id, safe=\"\")" in source


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
    assert "closed_panel_signal(" in source


def test_streamlit_closed_panel_shows_only_c_and_last_validated_signal_summary():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    start = source.index("if not st.session_state.panel_open:")
    end = source.index("st.stop()", start) + len("st.stop()")
    closed_state = source[start:end]
    assert 'st.button("C", key="open_control_hub")' in closed_state
    assert 'st.session_state.get("market_analysis_result")' in closed_state
    assert "closed_signal" in closed_state
    assert "closed_score" in closed_state
    assert "Controlador-Trader" not in closed_state
    assert "Histórico" not in closed_state
    assert "INDISPONÍVEL" not in closed_state


def test_closed_panel_uses_the_standalone_validated_signal_helper():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert "from presentation import closed_panel_signal" in source
    assert "closed_panel_signal(" in source



def test_streamlit_does_not_fill_unimplemented_modules_with_placeholder_copy():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert 'st.info(f"Módulo {module} selecionado.' not in source
    assert "A integração funcional deste módulo ainda não foi habilitada nesta prévia." not in source


def test_streamlit_leverage_control_persists_only_the_preference_without_execution_authority():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert 'st.checkbox(' in source
    assert '"Alavancagem",' in source
    assert 'key="leverage_enabled",' in source
    assert 'on_change=save_leverage_preference,' in source
    assert '"/api/preferences",' in source
    assert '"POST",' in source
    assert '{"leverage_enabled": bool(st.session_state.get("leverage_enabled", False))}' in source
    callback = source[source.index("def save_leverage_preference"):source.index("def fiscal_history_display_row")]
    assert '"real_execution_enabled"' not in callback
    assert '"autonomous_operation_enabled"' not in callback
    assert '"execution_allowed"' not in callback
    assert "Não ativa ordens, não altera margem e não concede autorização de execução." in source
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


def test_streamlit_operation_screen_aggregates_read_only_runtime_telemetry_and_keeps_execution_blocked():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    start = source.index('if module_name == "Operação":')
    end = source.index('if module_name in {"Memória", "Replay"}:', start)
    screen = source[start:end]
    for route in ("/api/health", "/api/connections", "/api/risk", "/api/runtime/analysis/latest"):
        assert route in screen
    for field in ("operational_observability", "market_data", "kill_switch", "recovery", "reconciliation", "runtime_health", "configured_limits"):
        assert field in screen
    assert "Execução permitida: NÃO" in screen
    assert "Execução REAL" in screen
    assert "não envia ordens" in screen
    assert 'api("/api/runtime/cycle", "POST"' not in screen
    assert 'api("/api/runtime/close", "POST"' not in screen
    assert 'api("/api/runtime/real/confirm", "POST"' not in screen


def test_streamlit_market_analysis_requires_demo_confirmation_and_never_enables_execution():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert 'api("/api/runtime/analysis", "POST"' in source
    assert 'confirmed = st.checkbox("Confirmo que esta análise é somente para estudo em DEMO/SIMULAÇÃO.")' in source
    analysis_screen = source[source.index("def show_market_analysis"):source.index("def show_readonly_module")]
    assert '"confirmed": True' not in analysis_screen
    assert '"filters_ok": True' not in analysis_screen
    assert "preferências de segurança do runtime são respeitadas" in analysis_screen
    assert 'Execução permitida: NÃO' in analysis_screen
    assert 'st.session_state.pop("market_analysis_result", None)' in analysis_screen
    assert analysis_screen.index('st.session_state.pop("market_analysis_result", None)') < analysis_screen.index('api("/api/runtime/analysis", "POST"')



def test_streamlit_market_analysis_shows_asset_session_and_news_readiness_without_authorizing_execution():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    screen = source[source.index("def show_market_analysis"):source.index("def show_replay")]
    assert 'api("/api/market/assets")' in screen
    assert 'item.get("weekend_capable") is True' in screen
    assert 'item.get("is_24_7_capable") is True' in screen
    assert 'item.get("quote_available") is True' in screen
    assert 'item.get("suitability_gaps")' in screen
    assert 'api("/api/news?limit=10")' in screen
    assert 'news.get("live") is not True' in screen
    assert "não está configurado" in screen.lower()
    assert 'api("/api/runtime/analysis", "POST"' in screen
    assert 'confirmed = st.checkbox("Confirmo que esta análise é somente para estudo em DEMO/SIMULAÇÃO.")' in screen
    assert "Execução permitida: NÃO" in screen
    assert "não significa mercado aberto agora" in screen.lower()
    assert 'api("/api/market/assets", "POST"' not in screen


def test_streamlit_preferences_never_submit_execution_authority_fields():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert source.count('if module_name == "Configurações":') == 1
    start = source.index('if module_name == "Configurações":')
    end = source.index('if module_name == "Escola / Tutorial / Onboarding":', start)
    preferences_screen = source[start:end]
    assert 'api("/api/preferences", "POST"' not in preferences_screen
    assert "st.checkbox(" not in preferences_screen
    assert "st.form(" not in preferences_screen
    assert 'safety_cols[1].metric("Execução REAL", "DESABILITADA")' in preferences_screen
    assert 'safety_cols[2].metric("Execução permitida", "NÃO")' in preferences_screen
    assert "Somente leitura" in preferences_screen


def test_streamlit_operational_screens_render_human_readable_summaries_without_raw_json_dump():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert "Central de Notificações" in source
    assert 'data.get("critical_count", 0)' in source
    assert "Limite de perda diária" in source
    assert "Kill Switch" in source
    assert "Fontes externas exigem validação" in source
    assert "Guia de primeiro uso" in source
    settings_start = source.index('if module_name == "Configurações":')
    settings_end = source.index('if module_name == "Escola / Tutorial / Onboarding":', settings_start)
    settings_screen = source[settings_start:settings_end]
    assert "Preferências sincronizadas do Ecossistema" in settings_screen
    assert "Somente leitura" in settings_screen
    assert "Salvar preferências" not in settings_screen
    assert "Salvar aparência" not in settings_screen
    assert "Salvar notificações" not in settings_screen
    assert 'api("/api/preferences", "POST"' not in settings_screen
    assert "st.json(data)" not in source


def test_streamlit_replay_uses_historical_mt5_demo_data_without_orders():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert 'api("/api/replay/mt5", "POST"' in source
    assert "Reproduzir histórico DEMO" in source
    assert "candles fechados" in source
    assert "Antecipação de candles futuros: NÃO" in source
    assert "Replay concluído sem envio de ordens." in source
    assert 'show_replay()' in source



def test_streamlit_simulator_discloses_backtest_assumptions_and_no_execution():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert 'api("/api/simulator/mt5/backtest", "POST"' in source
    assert "Executar backtest histórico DEMO" in source
    assert "Stop-loss · distância em unidades de preço" in source
    assert "Take-profit · distância em unidades de preço" in source
    assert "Quantidade em unidades/contratos" in source

    assert "Multiplicador do contrato" in source
    assert "Spread total em unidades de preço" in source
    assert "Execução permitida: NÃO" in source
    assert "O backtest não integra o Risk Manager" in source

def test_streamlit_foreign_pending_table_displays_fx_evidence_as_not_applied():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert '"Cotação informada (não aplicada)": item.get("fx_rate")' in source
    assert '"Data da cotação": item.get("fx_date")' in source
    assert '"Fonte da cotação": item.get("fx_source")' in source
    assert '"Método declarado": item.get("fx_conversion_method")' in source
    assert 'if fx_conversion_method == "NOT_CONVERTED":' in source
    assert 'if fx_method_signed == "NOT_CONVERTED":' in source
    assert "há uma cotação informada, mas o método está marcado como ainda não convertido." in source


def test_streamlit_documents_remote_single_link_and_persistent_mt5_requirements():
    readme = (PANEL_DIR / "README.md").read_text(encoding="utf-8")
    assert "Este acesso remoto ainda não está implantado nem validado." in readme
    assert "dois processos no computador" in readme
    assert "CONTROLADOR_BIND_HOST" in readme
    assert "Nunca publicar a porta 8000 diretamente na internet." in readme
    assert "armazenamento persistente e backups protegidos" in readme
    assert "máquina Windows/VPS continuamente ligada e validada" in readme
    assert "não mantém o MT5 conectado" in readme
    assert "Não foi feita implantação" in readme


def test_streamlit_setup_documents_runtime_openai_and_windows_mt5_dependencies():
    readme = (PANEL_DIR / "README.md").read_text(encoding="utf-8")
    assert "py -3.12 -m pip install -r requirements.txt" in readme
    assert "cliente OpenAI usado pelo Assistente" in readme
    assert "py -3.12 -m pip install MetaTrader5" in readme
    assert "terminal MT5 está instalado e em execução" in readme


def test_mt5_native_panel_is_real_mql5_client_of_shared_runtime():
    repo_root = PANEL_DIR.parent
    ea = (repo_root / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    readme = (PANEL_DIR / "README.md").read_text(encoding="utf-8")
    assert 'WebRequest(method,InpRuntimeUrl+path' in ea
    assert "void OnChartEvent(" in ea
    assert "void OnTimer()" in ea
    assert '"/api/health"' in ea
    assert '"/api/runtime/analysis"' in ea
    assert "não é executado dentro do gráfico MT5" in readme
    assert "não é uma imagem estática" in readme


def test_mt5_native_panel_restores_last_user_selected_visibility_state():
    repo_root = PANEL_DIR.parent
    ea = (repo_root / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    loader = ea.split("void LoadPanelVisibility(){", 1)[1].split("\n}", 1)[0]
    assert "GlobalVariableCheck(key)" in loader
    assert "GlobalVariableGet(key)>0.5" in loader
    assert "GlobalVariableSet(key,0.0)" in loader
    assert "panel_visible=false;" not in loader.split("else{", 1)[0]



def test_mt5_native_panel_never_offers_or_persists_real_mode():
    repo_root = PANEL_DIR.parent
    ea = (repo_root / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    assert 'SetButton(Obj("MODE_TOGGLE")' not in ea
    assert 'sparam==Obj("MODE_TOGGLE")' not in ea
    assert '\\"selected_mode\\":\\"DEMO\\"' in ea
    assert 'selected_mode="DEMO";' in ea



def test_streamlit_foreign_pending_queue_has_one_review_flow_without_legacy_duplicate():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert source.count('st.markdown("#### Revisão documental · Exterior")') == 1
    assert 'st.markdown("#### Pendências registradas")' not in source
    assert 'foreign_pending_data = api(f"/api/fiscal-reserve/pending?limit=50&offset={foreign_offset}")' in source
    assert '"/api/fiscal-reserve/pending/" + urllib.parse.quote(selected_foreign_pending_id)' in source



def test_fiscal_history_csv_exports_only_the_privacy_filtered_display_rows():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    helper = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "fiscal_history_display_row"
    )
    module = ast.Module(body=[helper], type_ignores=[])
    namespace = {"Any": Any, "json": json}
    exec(compile(module, "streamlit_panel/app.py", "exec"), namespace)
    display_row = namespace["fiscal_history_display_row"]

    foreign = display_row({
        "occurred_on": "2026-11-04",
        "category": "FOREIGN_FINANCIAL_INVESTMENT",
        "realized_result_brl": 9000,
        "reserve_rate": 20,
        "reserve_amount_brl": 1800,
        "reference": "foreign-1",
    })
    pending_brazilian = display_row({
        "occurred_on": "2026-11-04",
        "category": "BR_DAY_TRADE",
        "realized_result_brl": 500,
        "reserve_rate": 20,
        "reserve_amount_brl": 100,
        "reference": "br-pending-1",
        "notes": json.dumps({"tax_classification_status": "USER_DECLARED_PENDING_REVIEW"}),
    })

    assert foreign["Resultado (R$)"] == "—"
    assert foreign["Percentual de planejamento (%)"] == "—"
    assert foreign["Reserva estimada (R$)"] == "—"
    assert pending_brazilian["Resultado (R$)"] == 500
    assert pending_brazilian["Percentual de planejamento (%)"] == "—"
    assert pending_brazilian["Reserva estimada (R$)"] == "—"

    export_block = source[source.index('csv_buffer = io.StringIO'):source.index('st.caption("O arquivo é gerado nesta sessão')]
    assert "csv.DictWriter(" in export_block
    assert 'delimiter=";"' in export_block
    assert 'data="\\ufeff" + csv_buffer.getvalue()' in export_block
    assert "csv_writer.writerows(display_rows)" in export_block
    assert "fiscal_history_display_row(item)" in source



def test_streamlit_learning_modules_show_distinct_existing_data_without_trade_authority():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    learning_start = source.index('if module_name == "Laboratório":')
    onboarding_start = source.index('if module_name == "Escola / Tutorial / Onboarding":', learning_start)
    laboratory = source[learning_start:onboarding_start]
    assert 'if module_name == "Aprendizado":' in laboratory
    assert 'if module_name == "Descobertas":' in laboratory
    assert 'data.get("resources", [])' in laboratory
    assert 'data.get("learning_sources", [])' in laboratory
    assert 'data.get("activities", [])' in laboratory
    assert 'data.get("attempts", [])' in laboratory
    assert 'data.get("observations", [])' in laboratory
    assert "Materiais do laboratório" in laboratory
    assert "Histórico de tentativas" in laboratory
    assert "Observações" in laboratory
    assert "Execução permitida: NÃO." in laboratory
    assert "Descobertas não alteram sinais, filtros ou parâmetros de execução." in laboratory
    assert '("Laboratório", ("Laboratório de aprendizado", "/api/learning"))' not in source
    assert '"/api/learning"' in source



def test_streamlit_audit_module_uses_redacted_security_event_feed():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert '"Auditoria": ("Auditoria operacional", "/api/security/audit")' in source
    start = source.index('if module_name == "Auditoria":')
    end = source.index('if module_name == "Kill Switch":', start)
    audit_view = source[start:end]
    assert 'data.get("events", [])' in audit_view
    assert 'data.get("retention_limit", "—")' in audit_view
    assert "Hashes de cliente, endereços IP, credenciais e corpos de requisição não são exibidos." in audit_view
    assert "não substitui armazenamento centralizado nem auditoria externa" in audit_view
    assert "Execução permitida: NÃO" in audit_view



def test_streamlit_kill_switch_view_is_dedicated_and_read_only():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    start = source.index('if module_name == "Kill Switch":')
    end = source.index('if module_name == "Segurança":', start)
    view = source[start:end]
    assert 'data.get("operational_observability", {})' in view
    assert 'obs.get("kill_switch", {})' in view
    assert 'obs.get("recovery", {})' in view
    assert 'obs.get("reconciliation", {})' in view
    assert 'reconciliation.get("unknown_request_ids", [])' in view
    assert "Não altera o Kill Switch nem retoma operações." in view
    assert "Execução permitida: NÃO" in view


def test_streamlit_security_view_discloses_deployment_boundaries():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    start = source.index('if module_name == "Segurança":')
    end = source.index('if module_name in {"Operação"}:', start)
    view = source[start:end]
    assert 'data.get("production_storage", {})' in view
    assert 'data.get("production_operation_gate", {})' in view
    assert 'data.get("identity", data)' in view
    assert "não comprova implantação remota, backup externo ou isolamento multiusuário em produção" in view
    assert "Execução permitida: NÃO" in view



def test_streamlit_mt5_demo_connections_and_multibroker_views_are_distinct():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    start = source.index('if module_name == "MT5 DEMO / Simulação":')
    end = source.index('if module_name == "Kill Switch":', start)
    views = source[start:end]
    assert 'if module_name == "Conexões":' in views
    assert 'if module_name == "Multi-Broker":' in views
    assert 'data.get("ic_markets_mt5_demo", "NÃO CONFIRMADO")' in views
    assert 'data.get("execution_gateway", "NÃO CONFIRMADO")' in views
    assert 'data.get("cTrader", "FUTURO_NAO_BLOQUEANTE")' in views
    assert "não confirma que o terminal MT5 esteja aberto" in views
    assert "Não há evidência nesta resposta de uma segunda corretora conectada e validada." in views
    assert "REAL permanece DESABILITADO." in views


def test_streamlit_statistics_and_reports_have_distinct_aggregated_views():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    statistics_start = source.index('if module_name == "Estatísticas":')
    reports_start = source.index('if module_name == "Relatórios":', statistics_start)
    generic_start = source.index('if module_name in {"Motor de Decisão", "Estatísticas", "Relatórios"}:', reports_start)
    statistics_view = source[statistics_start:reports_start]
    reports_view = source[reports_start:generic_start]
    assert 'data.get("breakdowns", {})' in statistics_view
    assert '("by_symbol", "Por ativo")' in statistics_view
    assert '("by_timeframe", "Por timeframe")' in statistics_view
    assert '("by_signal", "Por sinal")' in statistics_view
    assert '("by_score_band", "Por faixa de pontuação")' in statistics_view
    assert 'data.get("periods", {})' in statistics_view
    assert "Taxa de vitória · operações encerradas" in statistics_view
    assert "relatório operacional" in reports_view.lower()
    assert "operational_report_csv_download" in reports_view
    assert 'delimiter=";"' in reports_view
    assert "report_buffer.getvalue()" in reports_view
    assert "controlador-trading-relatorio-operacional.csv" in reports_view
    assert "não inclui credenciais, dados bancários ou ordens" in reports_view
    assert "Execução permitida: NÃO · REAL: DESABILITADO" in statistics_view
    assert "Execução permitida: NÃO · REAL: DESABILITADO" in reports_view


def test_streamlit_notifications_screen_reads_full_history_without_mutations():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    start = source.index('if module_name == "Notificações":')
    end = source.index('if module_name == "Gestão de Risco":', start)
    view = source[start:end]
    assert 'api("/api/notifications/all")' in view
    assert 'data.get("critical_count", 0)' in view
    assert 'st.selectbox("Filtrar gravidade"' in view
    assert '"Atenção necessária": bool(item.get("requires_attention", False))' in view
    assert '"Bloqueante": bool(item.get("blocking", False))' in view
    assert "somente leitura" in view.lower()
    assert 'api("/api/notifications/all", "POST"' not in view
    assert "execução permitida: não · real: desabilitado" in view.lower()


def test_streamlit_risk_management_has_dedicated_read_only_limits_view():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert '"Gestão de Risco": ("Gestão de Risco", "/api/risk")' in source
    start = source.index('if module_name == "Gestão de Risco":')
    end = source.index('if module_name == "Simulador":', start)
    view = source[start:end]
    assert 'data.get("configured_limits", {})' in view
    assert 'limits.get("daily_loss_limit", "—")' in view
    assert 'limits.get("max_operations", "—")' in view
    assert 'limits.get("max_consecutive_losses", "—")' in view
    assert 'data.get("allowed") is True' in view
    assert 'data.get("news_provider", "NÃO CONFIGURADO")' in view
    assert "não altera limites" in view.lower()
    assert "execução permitida: não · real: desabilitado" in view.lower()
    assert 'api("/api/risk", "POST"' not in view


def test_streamlit_settings_view_reads_preferences_without_mutations():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert '"Configurações": ("Preferências do Ecossistema", "/api/preferences")' in source
    start = source.index('if module_name == "Configurações":')
    end = source.index('if module_name == "Motor de Decisão":', start)
    view = source[start:end]
    assert 'data.get("preferences", {})' in view
    assert 'prefs.get("default_symbol", "—")' in view
    assert 'prefs.get("default_timeframe", "—")' in view
    assert 'prefs.get("leverage_enabled", False)' in view
    assert 'safety_cols[1].metric("Execução REAL", "DESABILITADA")' in view
    assert "execução permitida: não · real: desabilitado" in view.lower()
    assert 'api("/api/preferences", "POST"' not in view


def test_streamlit_onboarding_shows_guided_steps_without_execution_authority():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert '"Escola / Tutorial / Onboarding": ("Primeiros passos", "/api/onboarding")' in source
    start = source.index('if module_name == "Escola / Tutorial / Onboarding":')
    end = source.index('if module_name == "Memória":', start)
    view = source[start:end]
    assert 'data.get("guide", {})' in view
    assert 'guide.get("steps", [])' in view
    assert 'step.get("purpose")' in view
    assert 'step.get("action_hint")' in view
    assert 'step.get("technical_details_hidden") is True' in view
    assert 'st.checkbox("Marcar etapa como revisada"' in view
    assert 'guide.get("execution_authorized") is not False' in view
    assert "marcação não altera o runtime" in view.lower()
    assert 'api("/api/onboarding", "POST"' not in view


def test_streamlit_memory_view_displays_recent_records_with_read_only_filters():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert '"Memória": ("Memória de decisões", "/api/memory?limit=50")' in source
    start = source.index('if module_name == "Memória":')
    end = source.index('if module_name == "Motor de Decisão":', start)
    view = source[start:end]
    assert 'data.get("records", [])' in view
    assert 'item.get("created_at", "—")' in view
    assert 'item.get("outcome")' in view
    assert 'item.get("outcome_source")' in view
    assert 'filter_cols[0].selectbox("Filtrar resultado anotado"' in view
    assert 'filter_cols[1].selectbox("Filtrar sinal"' in view
    assert 'item.get("confirmed") is True' in view
    assert "até 50 decisões recentes" in view
    assert "estudo manual" in view.lower()
    assert "Somente leitura" in view
    assert "execução permitida: não · real: desabilitado" in view.lower()
    assert 'api("/api/memory?limit=50", "POST"' not in view


def test_streamlit_decision_engine_uses_latest_read_only_analysis_snapshot():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert '"Motor de Decisão": ("Motor de Decisão · última análise", "/api/runtime/analysis/latest")' in source
    start = source.index('if module_name == "Motor de Decisão":')
    end = source.index('if module_name == "Operação":', start)
    view = source[start:end]
    assert 'data.get("available") is not True' in view
    assert 'latest.get("signal") or "AGUARDAR"' in view
    assert 'latest.get("candidate_signal")' in view
    assert "candidato não significa autorização de operação" in view
    assert "execução permitida: não · real: desabilitado" in view.lower()
    assert 'api("/api/runtime/analysis/latest", "POST"' not in view



def test_streamlit_fiscal_reserve_displays_day_week_month_year_estimates():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    assert 'periods = summary.get("periods", {})' in source
    assert '("day", "week", "month", "year")' in source
    assert '("Dia", "Semana", "Mês", "Ano")' in source
    assert 'col.metric(label, money(item.get("reserve_amount_brl")))' in source
    assert 'col.caption("Resultado: " + money(item.get("realized_result_brl")))' in source
    assert "ESTIMATIVA DE PLANEJAMENTO — não é imposto apurado ou devido." in source



def test_every_reference_navigation_module_has_a_functional_streamlit_route():
    config = json.loads((PANEL_DIR / "controlador_trader_referencia_visual.json").read_text(encoding="utf-8"))
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    configured_modules = {
        module
        for modules in config["open_state"]["tabs"].values()
        for module in modules
    }
    readonly_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "show_readonly_module":
            for child in ast.walk(node):
                if isinstance(child, ast.Assign):
                    for target in child.targets:
                        if isinstance(target, ast.Name) and target.id == "views" and isinstance(child.value, ast.Dict):
                            readonly_modules.update(
                                key.value for key in child.value.keys
                                if isinstance(key, ast.Constant) and isinstance(key.value, str)
                            )
    dedicated_routes = {"Análise de Mercado", "Replay", "Simulador"}
    special_routes = {"Financeiro"}
    assert configured_modules <= (readonly_modules | dedicated_routes | special_routes)
    assert 'if module == "Assistente do Ecossistema":' in source
    assert 'show_assistant()' in source
    assert 'elif module in {"Financeiro", "Reserva Fiscal"}:' in source
    assert "show_fiscal()" in source




def test_fiscal_summary_write_guard_rejects_invalid_aggregates_and_accepts_valid_summary():
    from math import isfinite

    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_valid_fiscal_summary"
    )
    isolated = ast.Module(body=[function], type_ignores=[])
    namespace = {"Any": Any, "isfinite": isfinite}
    exec(compile(isolated, str(PANEL_DIR / "app.py"), "exec"), namespace)
    validate = namespace["_valid_fiscal_summary"]

    valid = {
        "categories": {"BR_DAY_TRADE": {"rate": 20.0}},
        "total_reserved_brl": 200.0,
        "reserve_semantics": {
            "kind": "PLANNING_ESTIMATE_ONLY",
            "tax_liability_confirmed": False,
            "monthly_tax_assessment": False,
            "monthly_loss_offsets_calculated": False,
            "irrf_credits_calculated": False,
        },
        "periods": {
            key: {
                "start": "2026-11-01",
                "end": "2026-11-05",
                "realized_result_brl": 1000.0,
                "reserve_amount_brl": 200.0,
            }
            for key in ("day", "week", "month", "year")
        },
    }
    assert validate(valid) is True

    invalid_cases = []
    missing_period = {**valid, "periods": {key: value for key, value in valid["periods"].items() if key != "year"}}
    invalid_cases.append(missing_period)
    invalid_cases.append({**valid, "total_reserved_brl": float("inf")})
    invalid_cases.append({**valid, "categories": {"BR_DAY_TRADE": {"rate": True}}})
    invalid_cases.append({
        **valid,
        "reserve_semantics": {**valid["reserve_semantics"], "tax_liability_confirmed": True},
    })
    invalid_cases.append({
        **valid,
        "periods": {
            **valid["periods"],
            "month": {**valid["periods"]["month"], "reserve_amount_brl": float("nan")},
        },
    })
    invalid_cases.append({
        **valid,
        "periods": {
            **valid["periods"],
            "week": {**valid["periods"]["week"], "start": "2026-02-30"},
        },
    })
    invalid_cases.append({
        **valid,
        "periods": {
            **valid["periods"],
            "day": {**valid["periods"]["day"], "reserve_amount_brl": -0.01},
        },
    })
    invalid_cases.append({
        **valid,
        "periods": {
            **valid["periods"],
            "year": {
                **valid["periods"]["year"],
                "start": "2026-11-05",
                "end": "2026-11-01",
            },
        },
    })
    assert all(validate(candidate) is False for candidate in invalid_cases)


def test_fiscal_reserve_writes_are_disabled_when_summary_read_fails_or_is_incomplete():
    source = (PANEL_DIR / "app.py").read_text(encoding="utf-8")
    fiscal_start = source.index("def show_fiscal()")
    fiscal_end = source.index("\ndef ", fiscal_start + 1)
    fiscal = source[fiscal_start:fiscal_end]

    assert "summary_available = False" in fiscal
    assert "summary_available = _valid_fiscal_summary(summary)" in fiscal
    assert "def _valid_fiscal_summary(summary: Any) -> bool:" in source
    assert 'categories.get("BR_DAY_TRADE")' in source
    assert 'semantics.get("kind") != "PLANNING_ESTIMATE_ONLY"' in source
    assert '("day", "week", "month", "year")' in source
    assert 'not isfinite(value)' in source
    assert 'st.form_submit_button("Salvar percentual", disabled=not summary_available)' in fiscal
    assert 'st.form_submit_button("Registrar estimativa de planejamento", disabled=not summary_available)' in fiscal
    assert "lançamentos e alterações de percentual ficam bloqueados" in fiscal
