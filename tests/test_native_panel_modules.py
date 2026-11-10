from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EA = ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5"


def test_native_mt5_panel_exposes_reserva_fiscal_and_assistant_navigation():
    source = EA.read_text(encoding="utf-8")
    panel = source.split("void Panel()", 1)[1].split("void DeletePanel", 1)[0]
    events = source.split("void OnChartEvent", 1)[1]

    assert 'string area_labels[6]={"COCKPIT","ANÁLISE","ESTUDO","FISCAL","ASSIST.","CENTRAL"};' in source
    assert 'SetButton(area_button,area_labels[i]' in source
    assert 'SelectArea("RESERVA FISCAL")' in events
    assert 'SelectArea("ASSISTENTE DO ECOSSISTEMA")' in events
    assert 'SelectArea("CENTRAL")' in events
    assert "void RenderFiscal()" in source
    assert "void RenderAssistant()" in source
    assert "void RefreshFiscal()" in source
    assert "void RefreshAssistantStatus()" in source


def test_native_mt5_fiscal_view_uses_local_read_only_summary_and_preserves_separation():
    source = EA.read_text(encoding="utf-8")
    fiscal = source.split("void RefreshFiscal()", 1)[1].split("void RefreshAssistantStatus()", 1)[0]

    assert 'Http("GET","/api/fiscal-reserve/local?limit=20"' in fiscal
    assert 'JsonValue(r,"total_reserved_brl")' in fiscal
    assert 'JsonObjectValue(r,"foreign_pending","total")' in fiscal
    assert 'JsonObjectValue(r,"domestic_pending","total")' in fiscal
    assert "fora dos totais" in fiscal
    assert "sem calculo" in fiscal
    assert "REAL: BLOQUEADO" in fiscal


def test_native_mt5_assistant_requires_per_message_consent_and_persists_conversation():
    source = EA.read_text(encoding="utf-8")
    send = source.split("void SendAssistantMessage()", 1)[1].split("void RenderView()", 1)[0]
    events = source.split("void OnChartEvent", 1)[1]

    assert 'Http("GET","/api/assistant/local/status"' in source
    assert 'Http("POST","/api/assistant/local/chat"' in send
    assert "if(!assistant_consent_armed)" in send
    assert r'\"consent_to_openai\":true' in send
    assert "assistant_consent_armed=false;" in send
    assert "PersistAssistantConversation();" in send
    assert "LoadAssistantConversation();" in source
    assert 'Obj("ASSISTANT_CONSENT")' in events
    assert 'Obj("ASSISTANT_SEND")' in events
    assert "may_execute_orders" not in send
    assert "execution_allowed" not in send


def test_native_mt5_module_navigation_recreates_base_controls_without_background_polling():
    source = EA.read_text(encoding="utf-8")
    events = source.split("void OnChartEvent", 1)[1]
    timer = source.split("void OnTimer()", 1)[1].split("void OnChartEvent", 1)[0]
    health = source.split("void RefreshHealth()", 1)[1].split("void RefreshSecondary()", 1)[0]
    clear_fields = source.split("void ClearCockpitFields()", 1)[1].split("void ClearAssistantControls()", 1)[0]

    assert 'SelectArea("RESERVA FISCAL")' in events
    assert 'SelectArea("ASSISTENTE DO ECOSSISTEMA")' in events
    assert 'SelectArea("CENTRAL")' in events
    assert 'else if(active_view=="RESERVA") RefreshFiscal();' not in timer
    assert 'else if(active_view=="ASSISTENTE") RefreshAssistantStatus();' not in timer
    assert 'if(active_view=="RESERVA" || active_view=="ASSISTENTE" || active_view=="DECISION" || active_view=="KILL_SWITCH" || active_view=="UNAVAILABLE" || active_view=="MEMORIA" || active_view=="RISK" || active_view=="STATS" || active_view=="CONNECTIONS" || active_view=="ENVIRONMENT" || active_view=="SECURITY" || active_view=="REPORTS" || active_view=="AUDIT" || active_view=="FINANCE") return;' in health
    assert '"REC_REFRESH"' in clear_fields and '"REC_CLOSE"' in clear_fields



def test_native_mt5_navigation_never_routes_unimplemented_modules_to_unrelated_views():
    source = EA.read_text(encoding="utf-8")
    routing = source.split("string ViewForModule(", 1)[1].split("void RenderNavigation()", 1)[0]
    health = source.split("void RefreshHealth()", 1)[1].split("void RefreshMarketAssets()", 1)[0]

    # Decision engine has no dedicated native view yet; do not disguise analysis as it.
    assert 'if(module=="Motor de Decisão") return "ANALISE";' not in routing
    assert 'return "UNAVAILABLE";' in routing
    # An unavailable module must not create background health widgets over its notice.
    assert 'if(active_view=="UNAVAILABLE") return;' in health


def test_native_mt5_kill_switch_requires_reason_and_explicit_confirmation():
    source = EA.read_text(encoding="utf-8")
    routes = source.split("string ViewForModule(", 1)[1].split("void RenderNavigation()", 1)[0]
    activation = source.split("void ActivateKillSwitch()", 1)[1].split("void RefreshDecisionView()", 1)[0]
    events = source.split("void OnChartEvent", 1)[1]
    renderer = source.split("void RenderView()", 1)[1].split("void RefreshHealth()", 1)[0]

    assert 'if(module=="Kill Switch") return "KILL_SWITCH";' in routes
    assert 'Http("POST","/api/runtime/kill-switch/activate",body,response,code)' in activation
    assert 'if(!kill_switch_confirm_armed)' in activation
    assert 'if(reason=="" || StringLen(reason)>240)' in activation
    assert r'\"confirmed\":true' in activation
    assert 'if(activated=="true" && execution=="false")' in activation
    assert 'sparam==Obj("KILL_CONFIRM") && active_view=="KILL_SWITCH"' in events
    assert 'sparam==Obj("KILL_ACTIVATE") && active_view=="KILL_SWITCH"' in events
    assert 'KILL_REASON","KILL_CONFIRM","KILL_ACTIVATE' in renderer
    assert "deactivate" not in activation.lower()


def test_native_mt5_decision_engine_is_a_read_only_latest_analysis_view():
    source = EA.read_text(encoding="utf-8")
    routes = source.split("string ViewForModule(", 1)[1].split("void RenderNavigation()", 1)[0]
    decision = source.split("void RefreshDecisionView()", 1)[1].split("void RefreshRiskView()", 1)[0]
    health = source.split("void RefreshHealth()", 1)[1].split("void RefreshMarketAssets()", 1)[0]
    events = source.split("void OnChartEvent", 1)[1]

    assert 'if(module=="Motor de Decisão") return "DECISION";' in routes
    assert 'Http("GET","/api/runtime/analysis/latest","",r,code)' in decision
    assert 'JsonValue(r,"available")' in decision
    assert 'JsonValue(analysis,"signal")' in decision
    assert 'if(active_view=="DECISION") RefreshDecisionView();' in events
    assert 'active_view=="DECISION"' in health
    assert "nao cria ordem" in decision


def test_native_mt5_environment_and_statistics_are_not_misrepresented_as_other_modules():
    source = EA.read_text(encoding="utf-8")
    routing = source.split("string ViewForModule(", 1)[1].split("void RenderNavigation()", 1)[0]
    lab = source.split('}else if(active_view=="LAB"){', 1)[1].split('}else if(active_view=="ENSINO"){', 1)[0]

    assert 'if(module=="Ambiente MT5 DEMO / Simulação") return "LAB";' not in routing
    assert 'if(module=="Ambiente MT5 DEMO / Simulação") return "ENVIRONMENT";' in routing
    assert 'Http("GET","/api/health","",health,health_code)' in source
    assert 'Http("GET","/api/connections","",connections,connections_code)' in source
    assert 'active_view=="ENVIRONMENT"' in source
    assert 'else if(active_view=="ENVIRONMENT") RefreshEnvironmentView();' in source
    assert 'if(module=="Memória" || module=="Estatísticas") return "MEMORIA";' not in routing
    assert 'if(module=="Memória") return "MEMORIA";' in routing
    assert "Replay: indisponivel nesta interface" in lab
    assert "Replay: disponivel no laboratorio" not in lab
    assert "DEMO nao confirmado" in lab
    assert "Ambiente: DEMO / SIMULACAO" not in lab
    assert '(mode==""?"nao informado":mode)' in source
    assert '(mt5==""?"nao confirmado":mt5)' in source


def test_native_mt5_operational_actions_are_not_reused_by_non_operational_modules():
    source = EA.read_text(encoding="utf-8")
    render = source.split("void RenderView()", 1)[1].split("void RefreshHealth()", 1)[0]
    events = source.split("void OnChartEvent", 1)[1]

    assert 'if(active_view=="COCKPIT") RunCycle();' in events
    assert 'if(active_view=="COCKPIT") CloseCycle();' in events
    assert 'if(active_view=="CONFIG") SaveConfig();' in events
    assert 'if(active_view=="CONFIG") { leverage_enabled=!leverage_enabled; SaveConfig(); }' in events
    for view in ("ANALISE", "MEMORIA", "LAB", "ENSINO", "NOTIF"):
        section_start = render.find(f'active_view=="{view}"')
        assert section_start >= 0
        next_view = render.find('}else if(active_view==', section_start + 1)
        section = render[section_start: next_view if next_view >= 0 else len(render)]
        assert 'SetButton(Obj("CYCLE")' not in section
        assert 'SetButton(Obj("CLOSE")' not in section
        assert 'SetButton(Obj("SAVE")' not in section


def test_native_mt5_cockpit_retains_controls_after_module_action_reset():
    source = EA.read_text(encoding="utf-8")
    cockpit = source.split('if(active_view=="COCKPIT"){', 1)[1].split('}else if(active_view=="ANALISE"){', 1)[0]
    assert 'SetButton(Obj("CYCLE"),"RODAR CICLO DEMO"' in cockpit
    assert 'SetButton(Obj("CLOSE"),"FECHAR + RECONCILIAR"' in cockpit
    assert 'SetButton(Obj("SAVE"),"SALVAR CONFIG"' in cockpit
    assert 'ObjectDelete(0,Obj("CYCLE"))' not in cockpit

def test_native_mt5_assistant_paginates_the_complete_response_instead_of_silently_truncating():
    source = EA.read_text(encoding="utf-8")
    renderer = source.split("void RenderAssistantAnswer()", 1)[1].split("void RenderAssistant()", 1)[0]
    send = source.split("void SendAssistantMessage()", 1)[1].split("void RenderView()", 1)[0]
    events = source.split("void OnChartEvent", 1)[1]

    assert 'int page_size=330;' in renderer
    for index in range(1, 6):
        assert f'Obj("INFO{index}")' in renderer
    assert 'Obj("ASSISTANT_PREV")' in renderer
    assert 'Obj("ASSISTANT_NEXT")' in renderer
    assert 'Obj("ASSISTANT_PAGE")' in renderer
    assert 'assistant_answer=JsonValue(response,"answer");' in send
    assert "assistant_answer_page=0;" in send
    assert "RenderAssistantAnswer();" in send
    assert 'if(active_view=="ASSISTENTE" && assistant_answer_page>0)' in events
    assert 'if(active_view=="ASSISTENTE" && (assistant_answer_page+1)*330<StringLen(assistant_answer))' in events
    assert 'StringSubstr(answer,132,66)' not in send

def test_native_mt5_assistant_does_not_overwrite_persisted_answer_with_status_on_reentry():
    source = EA.read_text(encoding="utf-8")
    render = source.split("void RenderAssistant(){", 1)[1].split("void SendAssistantMessage()", 1)[0]

    assert 'if(assistant_answer==""){' in render
    assert "RefreshAssistantStatus();" in render
    assert "RenderAssistantAnswer();" in render
    assert render.index("RefreshAssistantStatus();") < render.index("}else{")
    assert render.index("}else{") < render.index("RenderAssistantAnswer();")

def test_native_risk_statistics_and_connections_modules_use_real_read_only_api_contracts():
    source = EA.read_text(encoding="utf-8")
    routes = source.split("string ViewForModule", 1)[1].split("void RenderNavigation", 1)[0]
    render = source.split("void RenderView(){", 1)[1].split("void RefreshHealth()", 1)[0]
    events = source.split("void OnChartEvent", 1)[1]

    assert 'if(module=="Gestão de Risco") return "RISK";' in routes
    assert 'if(module=="Estatísticas") return "STATS";' in routes
    assert 'if(module=="Conexões") return "CONNECTIONS";' in routes
    assert 'if(module=="Segurança") return "SECURITY";' in routes
    assert 'Http("GET","/api/health","",r,code)' in source
    assert 'active_view=="SECURITY"' in render
    assert 'else if(active_view=="SECURITY") RefreshSecurityView();' in events
    security = source.split("void RefreshSecurityView()", 1)[1].split("void RefreshFinanceOverview()", 1)[0]
    assert 'JsonValue(r,"trusted_identity_provider")' in security
    assert 'JsonValue(r,"tenant_isolation")' in security
    assert '"nao confirmado"' in security
    assert 'Http("GET","/api/risk","",r,code)' in source
    assert 'Http("GET","/api/statistics","",r,code)' in source
    assert 'Http("GET","/api/connections","",r,code)' in source
    assert 'active_view=="RISK"' in render
    assert 'active_view=="STATS"' in render
    assert 'active_view=="CONNECTIONS"' in render
    assert 'else if(active_view=="RISK") RefreshRiskView();' in events
    assert 'else if(active_view=="STATS") RefreshStatistics();' in events
    assert 'else if(active_view=="CONNECTIONS") RefreshConnections();' in events
    assert "Consulta informativa; nao autoriza execucao." in source
    assert "REAL: " in source


def test_native_statistics_and_connections_do_not_claim_unknown_values_are_zero_or_online():
    source = EA.read_text(encoding="utf-8")
    stats = source.split("void RefreshStatistics()", 1)[1].split("void RefreshRiskView()", 1)[0]
    connections = source.split("void RefreshConnections()", 1)[1].split("void ClearCockpitFields()", 1)[0]

    assert 'total==""?"nao informado":total' in stats
    assert 'rate==""?"nao informado":rate' in stats
    assert 'decision==""?"nao informado":decision' in connections
    assert 'mt5==""?"nao informado":mt5' in connections

def test_native_read_only_views_are_not_overwritten_by_cockpit_timer_refresh():
    source = EA.read_text(encoding="utf-8")
    health = source.split("void RefreshHealth()", 1)[1].split("void RefreshMarketAssets()", 1)[0]
    timer = source.split("void OnTimer()", 1)[1].split("void OnChartEvent", 1)[0]
    render = source.split("void RenderView(){", 1)[1].split("void RefreshHealth()", 1)[0]

    for view in ("MEMORIA", "RISK", "STATS", "CONNECTIONS", "ENVIRONMENT", "SECURITY"):
        assert f'active_view=="{view}"' in health
    assert 'if(active_view=="COCKPIT" && bid>0)' in timer
    for view in ("RISK", "STATS", "CONNECTIONS"):
        block = render.split(f'active_view=="{view}"', 1)[1].split('}else if', 1)[0]
        assert "ClearCockpitFields();" in block

def test_native_statistics_view_exposes_outcomes_and_daily_weekly_monthly_totals():
    source = EA.read_text(encoding="utf-8")
    stats = source.split("void RefreshStatistics()", 1)[1].split("void RefreshRiskView()", 1)[0]

    for field in ("actionable", "wins", "losses", "draws", "open"):
        assert f'JsonValue(r,"{field}")' in stats
    for period in ("daily", "weekly", "monthly"):
        assert f'JsonObjectValue(r,"periods","{period}")' in stats
    assert '"Hoje: "+(daily_total' in stats
    assert 'weekly_total==""?"?":weekly_total' in stats
    assert 'monthly_total==""?"?":monthly_total' in stats

def test_native_memory_view_reads_real_decision_records_and_paginates_them():
    source = EA.read_text(encoding="utf-8")
    memory = source.split("void RefreshMemory()", 1)[1].split("void RefreshStatistics()", 1)[0]
    renderer = source.split("void RenderMemoryPage()", 1)[1].split("void RefreshMemory()", 1)[0]
    view = source.split('active_view=="MEMORIA"', 1)[1].split('}else if', 1)[0]
    events = source.split("void OnChartEvent", 1)[1]

    assert 'Http("GET","/api/memory?limit=50","",r,code)' in memory
    assert 'ExtractJsonArrayObjects(r,"records",objects)' in memory
    for field in ("decision_id", "created_at", "symbol", "timeframe", "signal", "score", "outcome", "confirmed"):
        assert f'JsonValue(objects[i],"{field}")' in memory
    assert 'int page_size=5;' in renderer
    assert 'Obj("MEMORY_PREV")' in renderer
    assert 'Obj("MEMORY_NEXT")' in renderer
    assert 'Obj("MEMORY_PAGE")' in renderer
    assert 'else if(active_view=="MEMORIA") RefreshMemory();' in events
    assert 'if(active_view=="MEMORIA" && memory_page>0)' in events
    assert 'if(active_view=="MEMORIA" && (memory_page+1)*5<ArraySize(memory_records))' in events
    assert "RefreshSecondary();" not in view
    assert "auditoria" not in view.lower()


def test_native_memory_does_not_report_empty_or_malformed_api_response_as_success():
    source = EA.read_text(encoding="utf-8")
    memory = source.split("void RefreshMemory()", 1)[1].split("void RefreshStatistics()", 1)[0]

    assert 'if(!Http("GET","/api/memory?limit=50","",r,code))' in memory
    assert 'if(!ExtractJsonArrayObjects(r,"records",objects))' in memory
    assert 'if(id=="" || signal=="")' in memory
    assert 'memory_loaded=false;' in memory
    assert "Nenhum registro de decisao encontrado." in memory


def test_native_reports_and_audit_modules_are_real_read_only_screens():
    source = EA.read_text(encoding="utf-8")
    routing = source.split("string ViewForModule(", 1)[1].split("void RenderNavigation()", 1)[0]
    reports = source.split("void RefreshReports()", 1)[1].split("void RefreshAuditView()", 1)[0]
    audit = source.split("void RefreshAuditView()", 1)[1].split("void ClearCockpitFields()", 1)[0]
    events = source.split("void OnChartEvent", 1)[1]

    assert 'if(module=="Relatórios") return "REPORTS";' in routing
    assert 'if(module=="Auditoria") return "AUDIT";' in routing
    assert 'Http("GET","/api/reports?limit=50","",r,code)' in reports
    for field in ("total", "actionable", "wins", "losses", "win_rate"):
        assert f'JsonObjectValue(r,"summary","{field}")' in reports
    assert 'Http("GET","/api/security/audit?limit=50","",r,code)' in audit
    assert 'ExtractJsonArrayObjects(r,"events",objects)' in audit
    for field in ("count", "returned", "retention_limit", "persistence"):
        assert f'JsonValue(r,"{field}")' in audit
    assert 'else if(active_view=="REPORTS") RefreshReports();' in events
    assert 'else if(active_view=="AUDIT") RefreshAuditView();' in events
    assert "execution_allowed" not in reports
    assert "client_hash" not in audit


def test_native_finance_overview_uses_fiscal_api_without_claiming_cash_balance():
    source = EA.read_text(encoding="utf-8")
    routing = source.split("string ViewForModule(", 1)[1].split("void RenderNavigation()", 1)[0]
    finance = source.split("void RefreshFinanceOverview()", 1)[1].split("void RefreshReports()", 1)[0]
    events = source.split("void OnChartEvent", 1)[1]

    assert 'if(module=="Financeiro") return "FINANCE";' in routing
    assert 'Http("GET","/api/fiscal-reserve?limit=50&offset=0","",r,code)' in finance
    assert 'JsonValue(r,"total_reserved_brl")' in finance
    assert 'JsonObjectValue(r,"periods","month")' in finance
    assert 'JsonValue(month,"reserve_amount_brl")' in finance
    assert 'JsonValue(month,"realized_result_brl")' in finance
    assert 'Http("GET","/api/fiscal-reserve/domestic-pending/summary","",domestic_response,domestic_code)' in finance
    assert "nao representa saldo bancario ou equity" in finance
    assert "Pendencias fora dos totais" in finance
    assert 'else if(active_view=="FINANCE") RefreshFinanceOverview();' in events
