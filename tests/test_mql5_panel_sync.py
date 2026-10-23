from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deployment" / "sync_mql5_panel.ps1"


def test_mql5_sync_script_exists_and_is_self_contained():
    text = SCRIPT.read_text(encoding="utf-8")
    for required in (
        "terminal_info()",
        "data_path",
        "Controlador-Trading.mq5",
        "metaeditor64.exe",
        "/compile:",
        "errors",
        "warnings",
        "backup",
        "Copy-WithRetry",
        '"/log:$explicitLog"',
        "MetaEditor terminou sem gerar o EX5 esperado",
        "O EX5 não foi atualizado pela compilação",
        "timestamp anterior à compilação",
        "MetaEditor retornou código",
        "base64.b64decode",
        "Resultado validado pelos artefatos",
        "Log de compilação sem contagem inequívoca",
        "erros?",
        "avisos?",
        "EX5 ausente/desatualizado; recompilando.",
    ):
        assert required in text




def test_mql5_health_refresh_does_not_overwrite_active_section_content():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    health = panel.split("void RefreshHealth()", 1)[1].split("void RefreshMarketAssets()", 1)[0]
    assert 'SetLabel(Obj("RUNTIME")' in health
    assert 'SetLabel(Obj("INFO1")' not in health


def test_mql5_memory_record_counter_searches_json_key_without_extra_escaping():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    memory = panel.split("void RefreshMemory()", 1)[1].split("void SaveConfig()", 1)[0]
    assert 'StringFind(r,"\\"decision_id\\":",cursor)' in memory
    assert 'HTTP "+IntegerToString(code)' not in memory

def test_mql5_panel_has_single_repository_source():
    panel = ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5"
    legacy = ROOT / "mql5" / "Experts" / "ControladorTrading" / "ControladorTradingPanel.mq5"
    assert panel.is_file()
    assert not legacy.exists()


def test_controller_startup_calls_panel_sync():
    startup = (ROOT / "deployment" / "start_controlador_runtime.ps1").read_text(encoding="utf-8")
    assert "Sync-Mt5Panel" in startup
    assert "sync_mql5_panel.ps1" in startup


def test_mql5_panel_primes_runtime_and_refreshes_market_data_on_new_bars():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    init = panel.split("int OnInit()", 1)[1].split("int OnDeinit", 1)[0]
    timer = panel.split("void OnTimer()", 1)[1].split("void OnChartEvent", 1)[0]
    analyze = panel.split("void Analyze(bool render=true)", 1)[1].split("void RunCycle()", 1)[0]
    assert "Analyze(panel_visible);" in init
    assert "last_analysis_bar=iTime(_Symbol,_Period,0);" in init
    assert "current_bar!=last_analysis_bar" in timer
    assert "Analyze(active_view==\"COCKPIT\" || active_view==\"ANALISE\");" in timer
    assert "Analyze(false);" in timer
    assert '"/api/runtime/analysis"' in analyze
    assert "if(!render) return;" in analyze


def test_mql5_panel_uses_controlador_trading_brand_and_removes_watermark():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    assert '"Controlador Trading"' in panel
    assert '"Ecossistema • MT5 • Demo / simulação"' not in panel
    assert "RUNTIME REAL" not in panel
    assert "InpPanelWidth = 350" in panel
    assert "InpPanelHeight = 380" in panel
    assert "panel_x=12;" in panel
    assert "panel_width=MathMax(1,MathMin(InpPanelWidth,cw-24));" in panel
    assert "int available_height=MathMax(1,ch-panel_y-66);" in panel
    assert "int proportional_height=MathMax(1,(int)MathRound(ch*0.48));" in panel
    assert "panel_height=MathMax(1,MathMin(InpPanelHeight,MathMin(available_height,proportional_height)));" in panel
    assert "panel_y=18;" in panel
    assert 'ObjectSetString(0,name,OBJPROP_TEXT,"◯");' in panel
    assert 'ObjectSetString(0,letter,OBJPROP_TEXT,"C");' in panel
    assert 'Obj("SIDEBAR_BG")' in panel
    assert 'Obj("CONTENT_BG")' in panel
    assert 'Obj("PANEL_TOGGLE_FILL")' in panel
    assert "C'5,15,27'" in panel
    assert 'if(name==Obj("SUB")){' in panel
    assert 'SetButton(Obj("V10")' in panel
    assert 'SetEdit(Obj("SYM")' in panel
    assert 'SetEdit(Obj("TF")' in panel
    assert "CONTROLADOR TRADING" not in panel
    assert "WATERMARK_MARK" not in panel
    assert "WATERMARK_TEXT" not in panel
    assert 'Obj("WM")' not in panel
    assert "watermark_enabled" not in panel
    assert "preserveWatermark" not in panel
    assert "ToggleWatermark" not in panel


def test_mql5_sync_script_has_single_retry_helper_definition():
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.count("function Copy-WithRetry") == 1
    assert text.count("function Restore-File") == 1


def test_controller_supervisor_requires_health_before_healthy():
    startup = (ROOT / "deployment" / "start_controlador_runtime.ps1").read_text(encoding="utf-8")
    assert "Test-ControllerHealth" in startup
    assert "Wait-ControllerHealth" in startup
    assert "Write-SupervisorStatus 'STARTING'" in startup
    assert "function Test-ControllerSafety" in startup
    assert "http://127.0.0.1:8000/api/health/live" in startup
    assert "Write-SupervisorStatus 'HEALTHY' 'app.py ativo; liveness e health detalhado confirmados; REAL bloqueado.'" in startup
    assert "Write-SupervisorStatus 'ATTENTION'" in startup
    assert "Liveness do Controlador permaneceu indisponível" in startup
    assert "Start-Process" in startup
    assert "health_url = $healthUrl" in startup


def test_controller_supervisor_hardens_python_import_path():
    startup = (ROOT / "deployment" / "start_controlador_runtime.ps1").read_text(encoding="utf-8")
    assert "$env:PYTHONPATH" in startup
    assert "-WorkingDirectory $ProjectRoot" in startup
    assert "execution.mt5_demo_runtime_preflight" in startup


def test_controller_supervisor_recovers_unhealthy_existing_process():
    startup = (ROOT / "deployment" / "start_controlador_runtime.ps1").read_text(encoding="utf-8")
    assert "Instância existente não respondeu liveness" in startup
    assert "taskkill.exe /PID $existingController.ProcessId /T /F" in startup
    assert "RESTART_LIMIT_EXCEEDED" in startup


def test_deployment_resolves_python_to_an_absolute_executable():
    install = (ROOT / "deployment" / "install_windows_autostart.ps1").read_text(encoding="utf-8")
    bootstrap = (ROOT / "deployment" / "bootstrap_windows_runtime.ps1").read_text(encoding="utf-8")
    assert "Get-Command $PythonExe" in install
    assert "Get-Command $PythonExe" in bootstrap
    assert "Python não foi encontrado no PATH" in install
    assert "Python não foi encontrado no PATH" in bootstrap


def test_mql5_sync_does_not_reject_identical_binary_hash_after_successful_recompile():
    text = (ROOT / "deployment" / "sync_mql5_panel.ps1").read_text(encoding="utf-8")
    assert "($binaryHashBefore -and $binaryHashAfter -eq $binaryHashBefore)" not in text
    assert "timestamp anterior à compilação" in text


def test_mql5_panel_has_safe_visibility_toggle():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    assert "PANEL_TOGGLE" in panel
    assert "TogglePanel()" in panel
    assert "PanelVisibilityKey()" in panel
    timer = panel.split("void OnTimer()", 1)[1].split("void OnChartEvent", 1)[0]
    assert "if(!panel_visible){" in timer
    assert "Analyze(false);" in timer
    assert "execution" not in "TogglePanel" or "runtime" not in "TogglePanel"


def test_mql5_panel_off_does_not_render_on_init():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    init = panel.split("int OnInit()", 1)[1].split("int OnDeinit", 1)[0]
    assert "if(panel_visible){" in init
    assert "Panel();" in init
    assert "RenderView();" in init
    assert "}else{" in init
    assert "RefreshPanelToggle();" in init


def test_web_dashboard_uses_compact_separate_workspaces_without_runtime_view_persistence():
    web = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert '<nav class="nav">' in web
    assert "workspace-hidden" in web
    assert "function applyDefaultView(view)" in web
    assert 'href="#memoria">Memória</a>' in web
    assert 'href="#noticias">Notificações</a>' in web
    assert 'href="#config">Config.</a>' in web
    assert 'id="grafico"' in web
    assert 'id="painel"' in web
    assert "persistDefaultView" not in web
    assert "default_view" not in web


def test_web_watermark_is_not_rendered_until_approved_design_is_implemented():
    web = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert 'class="watermark-mark"' not in web
    assert '<div class="watermark-brand">' not in web

def test_mql5_sync_parses_numeric_error_and_warning_counts():
    text = SCRIPT.read_text(encoding="utf-8")
    assert r"(?i)(\d+)\s+(errors?|erros?)" in text
    assert r"(?i)(\d+)\s+(warnings?|avisos?)" in text
    assert r"(?i)(\\d+)\\s+" not in text

def test_mql5_sync_resolves_unique_data_folder_when_terminal_processes_duplicate():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "function Resolve-Mt5TerminalPath" in text
    assert "function Resolve-Mt5DataPath" in text
    assert "[string]$Mt5DataPath = $env:CONTROLADOR_MT5_DATA_PATH" in text
    assert "Get-ChildItem -LiteralPath $profilesRoot -Directory" in text
    assert "Mais de uma pasta de dados MT5 contém o painel" in text
    assert "Várias instâncias do MT5 estão ativas e nenhuma pasta de dados contém o painel" in text
    assert "$dataPath = Resolve-Mt5DataPath -RequestedPath $Mt5DataPath -TerminalPath $Mt5TerminalPath" in text
    assert "Mais de uma instância corresponde ao MT5 configurado" not in text

def test_mql5_panel_hide_preserves_c_toggle_and_deinit_removes_all_objects():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    delete = panel.split("void DeletePanel(", 1)[1].split("string JsonValue", 1)[0]
    toggle = panel.split("void TogglePanel()", 1)[1].split("void LoadPanelVisibility", 1)[0]
    timer = panel.split("void OnTimer()", 1)[1].split("void OnChartEvent", 1)[0]
    deinit = panel.split("void OnDeinit(", 1)[1].split("void OnTimer()", 1)[0]
    hidden = timer.split("if(!panel_visible){", 1)[1].split("return;", 1)[0]

    assert "bool preserveToggle=false)" in delete
    assert "if(preserveToggle) RefreshPanelToggle();" in delete
    assert "else DeletePanel(true);" in toggle
    assert "ApplyWatermark();" not in hidden
    assert "DeletePanel();" in deinit

def test_mql5_panel_toggle_tracks_layout_on_init_and_resize():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    render = panel.split("void Panel()", 1)[1].split("void DeletePanel", 1)[0]
    timer = panel.split("void OnTimer()", 1)[1].split("void OnChartEvent", 1)[0]
    visible_timer = timer.split("RefreshPanelLayout();", 1)[1]
    toggle = panel.split("void RefreshPanelToggle()", 1)[1].split("void TogglePanel()", 1)[0]
    assert render.index("RefreshPanelLayout();") < render.index("RefreshPanelToggle();")
    assert visible_timer.lstrip().startswith("RefreshPanelToggle();")
    assert "CHART_WIDTH_IN_PIXELS" in toggle
    assert "CHART_HEIGHT_IN_PIXELS" in toggle
    assert "int x=MathMax(8,cw-142);" in toggle
    assert "int y=MathMax(8,MathMin(ch-58,MathMax(8,ch-54)));" in toggle
    assert 'ObjectSetInteger(0,name,OBJPROP_XDISTANCE,x+21);' in toggle
    assert 'ObjectSetInteger(0,sig,OBJPROP_XDISTANCE,x+50);' in toggle
    assert 'ObjectSetInteger(0,quality,OBJPROP_XDISTANCE,x+82);' in toggle
    assert 'ObjectSetInteger(0,name,OBJPROP_YDISTANCE,y+21);' in toggle
    assert 'ObjectSetString(0,name,OBJPROP_TEXT,"◯");' in toggle
    assert 'ObjectSetString(0,letter,OBJPROP_TEXT,"C");' in toggle
    assert 'Obj("PANEL_CLOSE")' in toggle
    assert "panel_y=18;" in panel
def test_mql5_sync_requires_matching_source_and_binary_provenance_to_skip_compilation():
    text = SCRIPT.read_text(encoding="utf-8")
    assert '$provenance = "$binary.provenance.json"' in text
    assert "recordedProvenance.source_sha256" in text
    assert "recordedProvenance.binary_sha256" in text
    assert "if (-not $Force -and $sourceHash -eq $destinationHash -and $binaryUsable)" in text
    assert "source_sha256 = $sourceHash" in text
    assert "binary_sha256 = $binaryHashAfter" in text
    assert "Set-Content -LiteralPath $provenanceTemp -Encoding ASCII" in text
    assert text.count("Restore-File -Backup $backupProvenance -Target $provenance") == 7
    assert text.index("if ($binaryWriteTime -lt $compileStartedAt.AddSeconds(-2))") < text.index("binary_sha256 = $binaryHashAfter")

def test_mql5_signal_palette_keeps_buy_green_sell_luminous_amber():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    assert "C'0,255,70'" in panel
    assert "C'255,45,65'" in panel
    assert "C'255,176,0'" in panel
    assert panel.count("color c=SignalColor(signal);") == 2
def test_mql5_panel_preserves_in_progress_config_edits_on_redraw():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    edit = panel.split("void SetEdit(", 1)[1].split("void ApplyWatermark()", 1)[0]
    assert "bool created=(ObjectFind(0,name)<0);" in edit
    assert "if(created) ObjectSetString(0,name,OBJPROP_TEXT,text);" in edit
    assert "ObjectSetString(0,name,OBJPROP_TEXT,text);" not in edit.replace("if(created) ObjectSetString(0,name,OBJPROP_TEXT,text);", "")

def test_mql5_signal_labels_use_sentence_case_without_changing_signal_logic():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    labels = panel.split("string SignalLabel(string signal)", 1)[1].split("string NormalizeTimeframe", 1)[0]
    assert 'return "Comprar";' in labels
    assert 'return "Vender";' in labels
    assert 'return "Aguardar";' in labels
    assert 'SetLabel(Obj("SIGNAL"),SignalLabel(signal),20,176,10,c);' in panel
    assert 'string shown_signal=SignalLabel(last_signal);' in panel
def test_mql5_panel_uses_complete_tab_and_configuration_names():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    for label in ("COCKPIT", "ANÁLISE", "ESTUDO", "LABORATÓRIO", "REPLAY", "SIMULADOR", "MEMÓRIA", "ESTATÍSTICAS", "CONFIGURAÇÕES", "NOTIFICAÇÕES"):
        assert label in panel
    assert '"Salvar configurações"' in panel
    assert '"Encerrar e reconciliar"' in panel
    assert 'score+"%"' in panel
def test_mql5_c_toggle_remains_fixed_and_opens_or_closes_panel():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    toggle = panel.split("void TogglePanel()", 1)[1].split("void LoadPanelVisibility()", 1)[0]
    event = panel.split("void OnChartEvent(", 1)[1]
    refresh = panel.split("void RefreshPanelToggle()", 1)[1].split("void TogglePanel()", 1)[0]
    assert "panel_visible=!panel_visible;" in toggle
    assert "GlobalVariableSet(PanelVisibilityKey(),panel_visible?1.0:0.0);" in toggle
    assert 'if(sparam==Obj("PANEL_TOGGLE") || sparam==Obj("PANEL_TOGGLE_LETTER")) { TogglePanel(); return; }' in event
    assert 'if(sparam==Obj("PANEL_CLOSE")) { TogglePanel(); return; }' in event
    assert 'ObjectSetInteger(0,name,OBJPROP_XDISTANCE,x+21);' in refresh
    assert 'ObjectSetInteger(0,name,OBJPROP_YDISTANCE,y+21);' in refresh
def test_mql5_panel_configuration_toggles_persist_real_preferences():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    prefs = panel.split("void RefreshPreferences()", 1)[1].split("void RefreshNotifications()", 1)[0]
    save = panel.split("void SaveConfig()", 1)[1].split("void Analyze(", 1)[0]
    event = panel.split("void OnChartEvent(", 1)[1]
    assert "bool pref_closed_candle=true;" in panel
    assert "bool pref_require_filters=true;" in panel
    assert 'JsonNestedValue(r,"preferences","require_closed_candle")' in prefs
    assert 'JsonNestedValue(r,"preferences","require_filters")' in prefs
    assert 'JsonNestedValue(r,"preferences","leverage_enabled")' in prefs
    assert 'SetButton(Obj("ANALYZE"),"Confirmar candle: "+(pref_closed_candle?"Sim":"Não")' in prefs
    assert 'SetButton(Obj("CYCLE"),"Filtros obrigatórios: "+(pref_require_filters?"Sim":"Não")' in prefs
    assert 'SetButton(Obj("LEVERAGE_TOGGLE"),leverage_enabled?"ALAVANCAGEM: ON":"ALAVANCAGEM: OFF",202,175,177,28);' in prefs
    assert 'pref_closed_candle?"true":"false"' in save
    assert 'pref_require_filters?"true":"false"' in save
    assert 'leverage_enabled?"true":"false"' in save
    assert 'if(active_view=="CONFIG"){ pref_closed_candle=!pref_closed_candle;' in event
    assert 'if(active_view=="CONFIG"){ pref_require_filters=!pref_require_filters;' in event
    assert 'pref_closed_candle?"Sim":"Não"),20,316,172,30); SaveConfig();' in event
    assert 'pref_require_filters?"Sim":"Não"),202,316,177,30); SaveConfig();' in event
    assert 'else if(sparam==Obj("LEVERAGE_TOGGLE")) { leverage_enabled=!leverage_enabled; SaveLeveragePreference(); }' in event
    save_leverage = panel.split("void SaveLeveragePreference()", 1)[1].split("void SaveConfig()", 1)[0]
    assert 'string body="{\\"leverage_enabled\\":"+(leverage_enabled?"true":"false")+"}";' in save_leverage
    assert 'Http("POST","/api/preferences",body,r,code)' in save_leverage
    assert "SaveConfig();" not in save_leverage
    assert 'selected_mode' in save and 'DEMO' in save

def test_mql5_analysis_and_demo_cycle_use_saved_filter_preferences():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    analyze = panel.split("void Analyze(bool render=true)", 1)[1].split("void RunCycle()", 1)[0]
    cycle = panel.split("void RunCycle()", 1)[1].split("void CloseCycle()", 1)[0]
    assert 'pref_closed_candle?"true":"false"' in analyze
    assert 'pref_require_filters?"true":"false"' in analyze
    assert 'pref_closed_candle?"true":"false"' in cycle
    assert 'pref_require_filters?"true":"false"' in cycle
    assert 'confirmed\\":true' not in cycle
    assert 'filters_ok\\":true' not in cycle


def test_mql5_config_controls_do_not_overlap_status_text():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    prefs = panel.split("void RefreshPreferences()", 1)[1].split("void RefreshNotifications()", 1)[0]
    assert "MathRound(cw*0.34)" not in panel
    assert 'SetButton(Obj("ANALYZE"),"Confirmar candle: "+(pref_closed_candle?"Sim":"Não"),20,316,172,30);' in prefs
    assert 'SetButton(Obj("CYCLE"),"Filtros obrigatórios: "+(pref_require_filters?"Sim":"Não"),202,316,177,30);' in prefs
    assert 'SetButton(Obj("LEVERAGE_TOGGLE"),leverage_enabled?"ALAVANCAGEM: ON":"ALAVANCAGEM: OFF",202,175,177,28);' in prefs
    assert '20,390,9,' in prefs
    assert '20,478,9,' in prefs


def test_mql5_compact_signal_uses_sentence_case_for_correct_signal_colors():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    toggle = panel.split("void RefreshPanelToggle()", 1)[1].split("void TogglePanel()", 1)[0]
    assert 'color compact_color=(shown_signal=="Comprar")?C\'0,220,145\':(shown_signal=="Vender")?C\'255,82,105\':C\'255,176,0\';' not in toggle
    assert 'string compact_text=(shown_signal=="Comprar"?"↑  COMPRAR":(shown_signal=="Vender"?"↓  VENDER":(shown_signal=="Análise indisponível"?"ANÁLISE INDISPONÍVEL":"AGUARDAR")));' in toggle
    assert 'IsValidQualityScore(last_score)' in toggle
    assert 'Obj("COLLAPSED_QUALITY")' in toggle
    assert 'y+22' in toggle
    assert 'last_score+"%"' in toggle
    assert '+"  "+last_score+"%"' not in toggle
def test_mql5_demo_cycle_updates_compact_signal_and_uses_sentence_case():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    cycle = panel.split("void RunCycle()", 1)[1].split("void CloseCycle()", 1)[0]
    assert 'SetLabel(Obj("SIGNAL"),SignalLabel(signal),20,176,10,c);' in cycle
    assert "last_signal=signal; last_score=score; RefreshPanelToggle();" in cycle
    assert '"Ciclo de demonstração: "+SignalLabel(signal)' in cycle
def test_mql5_signal_quality_is_labeled_as_quality_not_generic_score():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    analyze = panel.split("void Analyze(bool render=true)", 1)[1].split("void RunCycle()", 1)[0]
    cycle = panel.split("void RunCycle()", 1)[1].split("void CloseCycle()", 1)[0]
    assert 'SetLabel(Obj("SCORE"),score==""?"":score+"%",20,206,9,c);' in analyze
    assert 'SetLabel(Obj("SCORE"),score==""?"":score+"%",20,206,9,c);' in cycle
    assert 'Obj("COLLAPSED_QUALITY")' in panel
    assert '"Decisão: "+SignalLabel(signal)+" • qualidade "+(score==""?"—":score)' in analyze

def test_mql5_demo_cycle_status_does_not_show_success_green_when_not_authorized():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    cycle = panel.split("void RunCycle()", 1)[1].split("void CloseCycle()", 1)[0]
    assert "if(!quality_valid){" in cycle
    assert 'SetLabel(Obj("INFO1"),"Análise indisponível; resultado do ciclo precisa ser confirmado",20,361,9,C\'255,176,0\');' in cycle
    assert 'allowed=="true"?C\'88,214,141\':C\'255,176,0\');' in cycle
    assert '"Ciclo de demonstração: "+SignalLabel(signal)' in cycle

def test_mql5_close_cycle_requires_runtime_confirmation_before_success_or_clearing_ids():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    close = panel.split("void CloseCycle()", 1)[1].split("int OnInit()", 1)[0]
    assert 'string closed=JsonValue(r,"closed");' in close
    assert 'string reconciliation=JsonValue(r,"reconciliation");' in close
    assert 'string terminal_state=JsonValue(r,"terminal_state");' in close
    assert 'StringToUpper(terminal_state);' in close
    assert 'bool has_reconciliation=(reconciliation!="" && reconciliation!="null" && StringSubstr(reconciliation,0,1)=="{");' in close
    assert 'bool reconciled=(has_reconciliation && (terminal_state=="COMPLETED" || terminal_state=="BLOCKED"));' in close
    assert 'string outcome_state=JsonValue(r,"reconciliation_state");' in close
    assert 'StringToUpper(outcome_state);' in close
    assert 'if(closed=="true" && reconciled)' in close
    assert 'last_cycle_id=""; last_external_id="";' in close
    assert '"Fechamento aceito; estado terminal ainda não confirmado."' in close
    assert '" Resultado financeiro ainda não verificado."' in close
    assert '"Fechamento não confirmado: "+StringSubstr' in close

def test_mql5_only_displays_runtime_quality_scores_from_1_to_100():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    assert "bool IsValidQualityScore(string score)" in panel
    quality = panel.split("bool IsValidQualityScore(string score)", 1)[1].split("void RefreshPanelToggle()", 1)[0]
    assert "if(score==\"\") return false;" in quality
    assert "if(ch<'0' || ch>'9') return false;" in quality
    assert "return value>=1 && value<=100;" in quality
    analyze = panel.split("void Analyze(bool render=true)", 1)[1].split("void RunCycle()", 1)[0]
    cycle = panel.split("void RunCycle()", 1)[1].split("void CloseCycle()", 1)[0]
    assert 'if(!quality_valid){ signal="ANALISE_INDISPONIVEL"; score=""; reason="Qualidade indisponível; análise não pode ser apresentada com segurança."; }' in analyze
    assert 'if(!quality_valid){ signal="ANALISE_INDISPONIVEL"; score=""; reason="Qualidade indisponível; análise não pode ser apresentada com segurança."; }' in cycle

def test_mql5_analysis_failure_clears_stale_compact_signal():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    analyze = panel.split("void Analyze(bool render=true)", 1)[1].split("void RunCycle()", 1)[0]
    failure = analyze.split('if(!Http("POST","/api/runtime/analysis"', 1)[1].split("\n   }", 1)[0]
    assert 'last_signal="ANALISE_INDISPONIVEL";' in failure
    assert 'last_score="";' in failure
    assert 'runtime_ok=false;' not in failure
    assert 'last_signal="ANALISE_INDISPONIVEL";' in failure
    assert 'last_score="";' in failure
    assert 'RefreshPanelToggle();' in failure
    assert '"Falha no runtime; sinal anterior descartado"' in failure

def test_mql5_failed_demo_cycle_clears_stale_signal():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    cycle = panel.split("void RunCycle()", 1)[1].split("void CloseCycle()", 1)[0]
    failure = cycle.split('if(!Http("POST","/api/runtime/cycle"', 1)[1].split("\n   }", 1)[0]
    assert 'last_signal="ANALISE_INDISPONIVEL";' in failure
    assert 'last_score="";' in failure
    assert 'last_cycle_id="";' in failure
    assert 'last_external_id="";' in failure
    assert '"Ciclo: não confirmado"' in failure
    assert '"Execução: não confirmada"' in failure
    assert 'RefreshPanelToggle();' in failure
    assert '"Ciclo não confirmado; sinal anterior descartado."' in failure

def test_mql5_signal_quality_and_reason_positions_match_after_redraw():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    base = panel.split("void Panel()", 1)[1].split("void DeletePanel", 1)[0]
    analyze = panel.split("void Analyze(bool render=true)", 1)[1].split("void RunCycle()", 1)[0]
    cycle = panel.split("void RunCycle()", 1)[1].split("void CloseCycle()", 1)[0]
    assert 'SetLabel(Obj("SIGNAL"),last_signal,20,176,10' in base
    assert 'SetLabel(Obj("SCORE"),IsValidQualityScore(last_score)?last_score+"%":"",20,206,9' in base
    assert 'SetLabel(Obj("REASON"),"Aguardando análise.",20,226,9' in base
    assert 'SetLabel(Obj("SIGNAL"),SignalLabel(signal),20,176,10,c);' in analyze
    assert 'SetLabel(Obj("SCORE"),score==""?"":score+"%",20,206,9' in analyze
    assert 'StringSubstr(reason==""?"Análise concluída pelo runtime.":reason,0,62),20,226,9' in analyze
    assert 'SetLabel(Obj("SIGNAL"),SignalLabel(signal),20,176,10,c);' in cycle
    assert 'SetLabel(Obj("SCORE"),score==""?"":score+"%",20,206,9' in cycle
    assert 'StringSubstr(reason==""?"Ciclo concluído.":reason,0,62),20,226,9' in cycle
def test_mql5_notifications_view_only_exposes_notification_refresh():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    notif = panel.split('}else if(active_view=="NOTIF"){', 1)[1].split('}else if(active_view=="CONFIG"){', 1)[0]
    assert 'SetButton(Obj("ANALYZE"),"Atualizar notificações"' in notif
    assert 'SetButton(Obj("CYCLE")' not in notif
    assert 'SetButton(Obj("SAVE")' not in notif
    assert 'SetButton(Obj("CLOSE")' not in notif
    render = panel.split("void RenderView()", 1)[1].split("void RefreshHealth()", 1)[0]
    assert 'string action_names[3]={Obj("CYCLE"),Obj("SAVE"),Obj("CLOSE")};' in render
    for control in ("CYCLE", "SAVE", "CLOSE"):
        assert f'Obj("{control}")' in render

def test_mql5_notifications_do_not_claim_unverified_analysis_or_event_refresh():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    notifications = panel.split("void RefreshNotifications()", 1)[1].split("void RefreshLearning()", 1)[0]
    assert '"Alertas importantes e críticos do ecossistema"' in notifications
    assert '"Abra um alerta para conferir os detalhes."' in notifications
    assert '"A análise de mercado é atualizada separadamente."' in notifications
    assert '"Atualização das notificações concluída"' not in notifications
    assert '"Analise operacional atualizada pelo runtime"' not in notifications


def test_mql5_notification_failure_clears_stale_success_details():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    notifications = panel.split("void RefreshNotifications()", 1)[1].split("void RefreshLearning()", 1)[0]
    failure = notifications.split("}else{", 1)[1]
    assert '"Notificações indisponíveis"' in failure
    assert 'SetLabel(Obj("INFO2"),"",20,381' in failure
    assert 'SetLabel(Obj("INFO3"),"",20,401' in failure
    assert 'SetLabel(Obj("INFO4"),"",20,421' in failure
    assert 'SetLabel(Obj("INFO5"),"",20,441' in failure

def test_mql5_health_does_not_claim_unknown_decision_engine_is_online():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    health = panel.split("void RefreshHealth()", 1)[1].split("void RefreshMarketAssets()", 1)[0]
    assert 'runtime_ok=(ok=="true" && health=="OK");' in health
    assert 'runtime_ok? "Sistema ONLINE"' not in health


def test_mql5_normalizes_signal_case_before_rendering_current_market_decision():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    analyze = panel.split("void Analyze(bool render=true)", 1)[1].split("void RunCycle()", 1)[0]
    cycle = panel.split("void RunCycle()", 1)[1].split("void CloseCycle()", 1)[0]
    assert analyze.count("StringToUpper(signal);") == 1
    assert cycle.count("StringToUpper(signal);") == 1
    assert 'if(!quality_valid){ signal="ANALISE_INDISPONIVEL"; score="";' in analyze
    assert 'if(!quality_valid){ signal="ANALISE_INDISPONIVEL"; score="";' in cycle


def test_mql5_study_failure_clears_stale_content_from_previous_refresh():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    study = panel.split("void RefreshLearning()", 1)[1].split("void RenderView()", 1)[0]
    failure = study.split('SetLabel(Obj("INFO1"),"Estudo indisponível"', 1)[1]
    for label in ("INFO2", "INFO3", "INFO4", "INFO5"):
        assert f'SetLabel(Obj("{label}"),"",20,' in failure


def test_mql5_notifications_view_avoids_transport_diagnostics_as_user_content():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    notifications = panel.split("void RefreshNotifications()", 1)[1].split("void RefreshLearning()", 1)[0]
    assert "Consulta HTTP concluída" not in notifications
    assert "conteúdo limitado ao resumo" not in notifications
    assert 'SetLabel(Obj("INFO2"),"Alertas importantes e críticos do ecossistema"' in notifications


def test_mql5_preferences_failure_clears_stale_values():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    preferences = panel.split("void RefreshPreferences()", 1)[1].split("void RefreshNotifications()", 1)[0]
    failure = preferences.split('if(!Http("GET","/api/preferences"', 1)[1].split("   }", 1)[0]
    assert '"Configurações indisponíveis"' in failure
    for label in ("INFO2", "INFO3", "INFO4", "INFO5"):
        assert f'SetLabel(Obj("{label}"),"",20,' in failure


def test_mql5_cycle_and_close_failures_hide_transport_codes_from_panel_copy():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    cycle = panel.split("void RunCycle()", 1)[1].split("void CloseCycle()", 1)[0]
    close = panel.split("void CloseCycle()", 1)[1].split("int OnInit()", 1)[0]
    assert "Ciclo indisponível; runtime não confirmou resultado" in cycle
    assert "Fechamento falhou ou foi bloqueado" in close
    assert 'HTTP "+IntegerToString(code)' not in cycle
    assert 'HTTP "+IntegerToString(code)' not in close


def test_mql5_panel_uses_navy_cyan_ecosystem_palette_and_contrasting_c():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    assert "ObjectSetInteger(0,bg,OBJPROP_BGCOLOR,C'8,17,30');" in panel
    assert "ObjectSetInteger(0,bg,OBJPROP_BORDER_COLOR,C'0,150,190');" in panel
    assert "ObjectSetInteger(0,letter,OBJPROP_COLOR,C'0,215,255');" in panel
    assert 'ObjectSetString(0,name,OBJPROP_TEXT,"◯");' in panel
def test_mql5_health_status_stays_below_navigation_tabs():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    base = panel.split("void Panel()", 1)[1].split("void DeletePanel", 1)[0]
    health = panel.split("void RefreshHealth()", 1)[1].split("void RefreshMarketAssets()", 1)[0]
    assert 'SetLabel(Obj("RUNTIME"),"Sistema indisponível",20,126,10' in base
    assert 'SetLabel(Obj("RUNTIME"),"Sistema INDISPONÍVEL",20,126,10' in health
    assert 'SetLabel(Obj("RUNTIME"),runtime_ok?"Sistema ONLINE":"Sistema INDISPONÍVEL",20,126,10' in health
    assert '20,146,10,C\'88,214,141\'' in health
    assert '20,104,10' not in health
    assert '20,124,10' not in health

def test_mql5_compact_layout_uses_dedicated_vertical_positions_and_hides_secondary_rows():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    scale = panel.split("int SX(", 1)[1].split("void RefreshPanelLayout()", 1)[0]
    label = panel.split("void SetLabel(", 1)[1].split("void SetButton(", 1)[0]
    button = panel.split("void SetButton(", 1)[1].split("void SetEdit(", 1)[0]
    assert "bool panel_compact=false;" in panel
    assert "panel_compact=(panel_height<340 || panel_width<350);" in panel
    assert "int CompactY(int y){ return (int)MathRound(y*panel_sy); }" in scale
    assert "ContentX(int x)" in scale
    assert "ContentW(int w)" in scale
    assert "ContentY(int y)" in scale
    assert "ContentScale()" in scale
    assert 'Obj("WM")' not in button
    assert 'if(panel_compact && secondary) text="";' not in label
    assert 'StringFind(name,Obj("INFO1"))==0' not in label
    assert 'StringFind(name,Obj("INFO5"))==0' not in label
    assert "return 258;" not in scale
    assert "panel_compact?MathMax(21" in panel
def test_mql5_panel_update_has_no_watermark_or_watermark_setting():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    assert "CONTROLADOR TRADING" not in panel
    assert "WATERMARK_MARK" not in panel
    assert "WATERMARK_TEXT" not in panel
    assert 'Obj("WM")' not in panel
    assert "watermark_enabled" not in panel
    assert "ToggleWatermark" not in panel


def test_mql5_narrow_panel_navigation_uses_two_rows_without_horizontal_crushing():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    button = panel.split("void SetButton(", 1)[1].split("void SetEdit(", 1)[0]
    assert 'bool nav=(name==Obj("V1")' in button
    assert 'name==Obj("V8")' in button
    assert 'name==Obj("V10")' in button
    assert "int nav_area=MathMax(1,panel_height-58);" in button
    assert "int nav_step=MathMax(1,MathMin(25,nav_area/10));" in button
    assert "button_h=MathMax(1,MathMin(22,nav_step-1));" in button
    assert "button_y=panel_y+50+(index-1)*nav_step;" in button
    assert "if(panel_height<180){ button_font=6; }" in button
    assert "button_w=MathMax(1,SidebarWidth()-10);" in button
    assert "int index=0;" in button
def test_mql5_narrow_navigation_parses_numeric_tab_suffix():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    button = panel.split("void SetButton(", 1)[1].split("void SetEdit(", 1)[0]
    for index in range(1, 11):
        assert f'Obj("V{index}")' in button
        assert f'index={index};' in button
    assert "button_y=panel_y+50+(index-1)*nav_step;" in button
def test_mql5_compact_mode_hides_market_edit_fields_to_preserve_action_space():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    edit = panel.split("void SetEdit(", 1)[1].split("void RefreshPanelToggle()", 1)[0]
    label = panel.split("void SetLabel(", 1)[1].split("void SetButton(", 1)[0]
    assert "ContentX(x)" in edit
    assert "ContentY(y)" in edit
    assert "ContentW(w)" in edit
    assert "MathMax(22,SH(h))" in edit
    assert "OBJPROP_XSIZE,panel_compact?1:SW(w)" not in edit
    assert 'ObjectSetString(0,name,OBJPROP_TEXT,"");' not in edit
    assert 'if(panel_compact && secondary) text="";' not in label

def test_mql5_awaiting_signal_is_amber_even_after_panel_redraw():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    base = panel.split("void Panel()", 1)[1].split("void DeletePanel", 1)[0]
    toggle = panel.split("void RefreshPanelToggle()", 1)[1].split("void TogglePanel()", 1)[0]
    colors = panel.split("color SignalColor(string signal)", 1)[1].split("string CurrentLeverageText()", 1)[0]
    assert 'SetLabel(Obj("SIGNAL"),last_signal,20,176,10,SignalColor(last_signal));' in base
    assert 'color compact_color=SignalColor(last_signal);' in toggle
    assert 'return C\'255,176,0\';' in colors


def test_mql5_open_panel_shows_actual_account_leverage_not_a_hardcoded_value():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    leverage = panel.split("string CurrentLeverageText()", 1)[1].split("bool IsValidQualityScore", 1)[0]
    assert "AccountInfoInteger(ACCOUNT_LEVERAGE)" in leverage
    assert 'return "Alavancagem da conta: indisponível";' in leverage
    assert 'return "Alavancagem da conta: 1:"+IntegerToString((int)leverage);' in leverage
    assert 'SetLabel(Obj("LEVERAGE"),CurrentLeverageText(),12,58,9' in panel


def test_mql5_collapse_and_init_clean_panel_only_objects_before_rebuilding_compact_view():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    init = panel.split("int OnInit()", 1)[1].split("void OnDeinit", 1)[0]
    delete = panel.split("void DeletePanel(", 1)[1].split("string JsonValue", 1)[0]
    toggle = panel.split("void RefreshPanelToggle()", 1)[1].split("void TogglePanel()", 1)[0]
    assert "DeletePanel();" in init
    assert 'if(StringFind(n,P)!=0) continue;' in delete
    assert "ObjectDelete(0,n);" in delete
    assert 'ObjectSetString(0,sig,OBJPROP_TEXT,panel_visible?"":compact_text);' in toggle
    assert 'ObjectSetString(0,quality,OBJPROP_TEXT,(panel_visible || !IsValidQualityScore(last_score))?"":last_score+"%");' in toggle
    assert 'else if(ObjectFind(0,close_name)>=0) ObjectDelete(0,close_name);' in toggle


def test_mql5_panel_hides_redundant_chart_signal_explanations_from_cockpit():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    cockpit = panel.split('if(active_view=="COCKPIT"){', 1)[1].split('}else if(active_view=="ANALISE"){', 1)[0]
    assert '"Decisão atual: consulte o sinal junto ao C"' not in panel
    assert '"Sinal atual exibido ao lado do C"' not in panel
    assert 'SetLabel(Obj("INFO2"),"",20,381' in cockpit
    assert 'SetLabel(Obj("INFO4"),"",20,421' in cockpit


def test_mql5_source_does_not_embed_pr415_file_name_as_chart_text():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    assert "ControladorTradingPR415" not in panel
    assert '"label"' not in panel.lower()


def test_mql5_expanded_panel_stays_at_top_and_does_not_cover_bottom_sell_buy_controls():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    layout = panel.split("void RefreshPanelLayout()", 1)[1].split("void SetLabel(", 1)[0]
    assert "panel_y=18;" in layout
    assert "panel_visible?MathMax(8,ch-panel_height-66):18" not in layout



def test_mql5_panel_geometry_clamps_to_small_chart_and_keeps_trade_controls_clear():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    layout = panel.split("void RefreshPanelLayout()", 1)[1].split("void SetLabel(", 1)[0]
    assert "panel_width=MathMax(1,MathMin(InpPanelWidth,cw-24));" in layout
    assert "panel_y=18;" in layout
    assert "ch-panel_y-66" in layout
    assert "panel_height=MathMax(1,MathMin(InpPanelHeight,MathMin(available_height,proportional_height)));" in layout
    assert 'px=panel_x+(panel_width<320?MathMax(52,panel_width-112):MathMin(218,MathMax(155,panel_width-185))); py=panel_y+10; fs=9;' in panel


def test_mql5_narrow_header_prioritizes_signal_and_panel_background_dimensions_stay_positive():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    label = panel.split("void SetLabel(", 1)[1].split("void SetButton(", 1)[0]
    layout = panel.split("void Panel()", 1)[1].split("void DeletePanel", 1)[0]
    assert "if(panel_width<320) text=\"\";" in label
    assert "panel_width<320?MathMax(52,panel_width-112)" in label
    assert "OBJPROP_YSIZE,MathMax(1,panel_height-57)" in layout
    assert layout.count("OBJPROP_YSIZE,MathMax(1,panel_height-57)") == 2


def test_mql5_reads_quality_from_nested_api_contract_and_cycle_wrapper():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    analyze = panel.split("void Analyze(bool render=true)", 1)[1].split("void RunCycle()", 1)[0]
    cycle = panel.split("void RunCycle()", 1)[1].split("void CloseCycle()", 1)[0]
    assert 'NormalizeQualityScore(JsonNestedValue(r,"quality","score"))' in analyze
    assert 'string runtime=JsonObject(r,"runtime");' in cycle
    assert 'NormalizeQualityScore(JsonNestedValue(runtime,"quality","score"))' in cycle
    assert 'string allowed=JsonValue(r,"execution_allowed");' in cycle
    assert 'JsonValue(runtime,"cycle_id")' in cycle
    assert "double value=StringToDouble(raw);" in panel
    assert "return IntegerToString(rounded);" in panel


def test_mql5_shows_analysis_unavailable_separately_from_wait():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    assert 'return "Análise indisponível";' in panel
    assert 'shown_signal=="Análise indisponível"?"ANÁLISE INDISPONÍVEL"' in panel
    assert 'last_signal="ANALISE_INDISPONIVEL";' in panel
    assert 'SetLabel(Obj("SCORE"),"",20,206,9,clrWhite);' in panel


def test_mql5_open_panel_is_capped_below_half_chart_height():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    assert "input int    InpPanelWidth = 350;" in panel
    assert "input int    InpPanelHeight = 380;" in panel
    assert "int proportional_height=MathMax(1,(int)MathRound(ch*0.48));" in panel
    assert "int panel_width=350;" in panel
    assert "int panel_height=380;" in panel


def test_mql5_leverage_toggle_stays_available_across_panel_sections():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    render = panel.split("void RenderView()", 1)[1].split("void RefreshHealth()", 1)[0]
    refresh = panel.split("void RefreshLeveragePreference()", 1)[1].split("void RefreshPreferences()", 1)[0]
    timer = panel.split("void OnTimer()", 1)[1].split("void OnChartEvent", 1)[0]

    assert 'string action_names[3]={Obj("CYCLE"),Obj("SAVE"),Obj("CLOSE")};' in render
    assert 'SetButton(Obj("LEVERAGE_TOGGLE"),leverage_enabled?"ALAVANCAGEM: ON":"ALAVANCAGEM: OFF",202,175,177,28);' in render
    assert 'JsonNestedValue(r,"preferences","leverage_enabled")' in refresh
    assert 'RefreshLeveragePreference();' in timer
    assert 'if(active_view=="CONFIG") RefreshPreferences();' in timer
