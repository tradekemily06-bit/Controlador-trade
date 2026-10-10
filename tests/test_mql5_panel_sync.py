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


def test_mql5_panel_uses_controlador_trading_brand_and_watermark_toggle():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    assert '#property description "Controlador Trading' in panel
    assert '"ECOSSISTEMA • DEMO / SIMULACAO"' in panel
    assert "RUNTIME REAL" not in panel
    assert '"CONTROLADOR TRADING"' in panel
    assert '"WATERMARK_MARK"' in panel
    assert "ObjectSetInteger(0,mark,OBJPROP_FONTSIZE,wm_icon_size)" in panel
    assert "ObjectSetInteger(0,name,OBJPROP_FONTSIZE,wm_text_size)" in panel
    assert "wm_scale=MathMin((double)w/1360.0,(double)h/760.0);" in panel
    assert "InpPanelWidth = 440" in panel
    assert "InpPanelHeight = 440" in panel
    assert "panel_x=12;" in panel
    assert "panel_y=MathMax(12,ch-panel_height-52);" in panel
    assert "int center_x=w/2;" in panel
    assert "MathRound(h*0.52)" in panel
    assert "panel_sx=(double)panel_width/540.0;" in panel
    assert "MathMax(540,InpPanelWidth)" in panel
    assert "OBJPROP_ANGLE,18.0" not in panel
    assert "ToggleWatermark" in panel
    assert "GlobalVariableSet(WatermarkKey()" in panel
    # In collapsed mode the watermark switch stays top-right, clear of C and its signal.
    assert "int x=panel_visible?panel_x+panel_width-118:MathMax(4,cw-80);" in panel
    assert "int y=panel_visible?panel_y+42:12;" in panel


def test_mql5_sync_script_has_single_retry_helper_definition():
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.count("function Copy-WithRetry") == 1
    assert text.count("function Restore-File") == 1


def test_controller_supervisor_requires_health_before_healthy():
    startup = (ROOT / "deployment" / "start_controlador_runtime.ps1").read_text(encoding="utf-8")
    assert "Test-ControllerHealth" in startup
    assert "Wait-ControllerHealth" in startup
    assert "Write-SupervisorStatus 'STARTING'" in startup
    assert "Write-SupervisorStatus 'HEALTHY' 'app.py ativo e /api/health respondeu 2xx.'" in startup
    assert "Start-Process" in startup
    assert "health_url = $healthUrl" in startup


def test_controller_supervisor_hardens_python_import_path():
    startup = (ROOT / "deployment" / "start_controlador_runtime.ps1").read_text(encoding="utf-8")
    assert "$env:PYTHONPATH" in startup
    assert "-WorkingDirectory $ProjectRoot" in startup
    assert "execution.mt5_demo_runtime_preflight" in startup


def test_controller_supervisor_recovers_unhealthy_existing_process():
    startup = (ROOT / "deployment" / "start_controlador_runtime.ps1").read_text(encoding="utf-8")
    assert "Instância existente não respondeu /api/health" in startup
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
    assert "if(panel_visible){\n      RefreshHealth();\n      RefreshSecondary();\n      RefreshMarketAssets();\n   }" in init
    assert "Analyze(panel_visible);" in init


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


def test_web_watermark_is_centered_horizontal_and_includes_brand_mark():
    web = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert '<div class="watermark-brand">' in web
    assert 'class="watermark-mark"' in web
    assert "transform:rotate(-18deg)" not in web
    assert "opacity:.035" in web

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

def test_mql5_panel_hide_preserves_watermark_and_deinit_removes_all_objects():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    delete = panel.split("void DeletePanel(", 1)[1].split("string JsonValue", 1)[0]
    toggle = panel.split("void TogglePanel()", 1)[1].split("void LoadPanelVisibility", 1)[0]
    timer = panel.split("void OnTimer()", 1)[1].split("void OnChartEvent", 1)[0]
    deinit = panel.split("void OnDeinit(", 1)[1].split("void OnTimer()", 1)[0]
    hidden = timer.split("if(!panel_visible){", 1)[1].split("return;", 1)[0]

    assert "bool preserveWatermark=false,bool preserveToggle=false" in delete
    assert 'n==Obj("WATERMARK_MARK") || n==Obj("WATERMARK_TEXT")' in delete
    assert "if(preserveToggle) RefreshPanelToggle();" in delete
    assert "else DeletePanel(true,true);" in toggle
    assert "ApplyWatermark();" in hidden
    assert "DeletePanel();" in deinit



def test_mql5_panel_toggle_tracks_layout_on_init_and_resize():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    render = panel.split("void Panel()", 1)[1].split("void RenderView()", 1)[0]
    timer = panel.split("void OnTimer()", 1)[1].split("void OnChartEvent", 1)[0]
    visible_timer = timer.split("   RefreshPanelLayout();", 1)[1]
    assert render.index("RefreshPanelLayout();") < render.index("RefreshPanelToggle();")
    assert visible_timer.lstrip().startswith("RefreshPanelToggle();")
    assert "int toggle_x=panel_visible?panel_x+panel_width-c_size-8:12;" in panel
    assert 'ObjectSetString(0,name,OBJPROP_TEXT,"Ⓒ");' in panel


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


def test_mql5_panel_has_compact_c_toggle_and_dynamic_signal_when_closed():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    toggle = panel.split("void RefreshPanelToggle()", 1)[1].split("void TogglePanel()", 1)[0]
    assert 'ObjectSetString(0,name,OBJPROP_TEXT,"Ⓒ");' in toggle
    assert 'Obj("PANEL_SIGNAL")' in toggle
    assert 'signal=="COMPRA" || signal=="COMPRAR"' in toggle
    assert 'signal=="VENDA" || signal=="VENDER"' in toggle
    assert 'signal="AGUARDAR"' in toggle
    assert "panel_visible?panel_x+panel_width-c_size-8:12" in toggle
    assert '"CONTROLADOR TRADING"' in panel
    assert '"ECOSSISTEMA • DEMO / SIMULACAO"' in panel
    assert '"Integrado"' not in panel


def test_mql5_panel_preserves_dynamic_signal_when_closed():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    toggle = panel.split("void RefreshPanelToggle()", 1)[1].split("void TogglePanel()", 1)[0]
    assert 'string current_signal="AGUARDAR";' in panel
    assert "string signal=current_signal;" in toggle
    assert 'signal="COMPRAR"' in toggle
    assert 'signal="VENDER"' in toggle
    assert 'signal="AGUARDAR"' in toggle
    assert "current_signal=(signal==" in panel
    assert 'ObjectSetString(0,name,OBJPROP_TEXT,"Ⓒ");' in toggle


def test_mql5_demo_cycle_updates_closed_c_signal():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    cycle = panel.split("void RunCycle()", 1)[1].split("void CloseCycle()", 1)[0]
    assert 'current_signal=(signal=="COMPRA" || signal=="COMPRAR")?' in cycle
    assert 'SetLabel(Obj("SIGNAL"),current_signal' in cycle
    assert "RefreshPanelToggle();" in cycle


def test_mql5_hidden_analysis_updates_c_signal_before_render_guard():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    analyze = panel.split("void Analyze(bool render=true)", 1)[1].split("void RunCycle()", 1)[0]
    assert analyze.index('string signal=JsonValue(r,"signal");') < analyze.index("if(!render) return;")
    assert analyze.index("current_signal=(signal==") < analyze.index("if(!render) return;")
    assert analyze.index("RefreshPanelToggle();") < analyze.index("if(!render) return;")
    assert "color c=current_signal==\"COMPRAR\"?" in analyze


def test_mql5_failed_analysis_clears_stale_signal_to_wait():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    analyze = panel.split("void Analyze(bool render=true)", 1)[1].split("void RunCycle()", 1)[0]
    failure = analyze.split('if(!Http("POST","/api/runtime/analysis",body,r,code)){', 1)[1].split("   }", 1)[0]
    assert 'runtime_ok=false;' in failure
    assert 'current_signal="AGUARDAR";' in failure
    assert "RefreshPanelToggle();" in failure
    assert 'SetLabel(Obj("SIGNAL"),current_signal' in failure
    assert "Analise indisponivel" in failure

def test_mql5_win_loss_view_refreshes_runtime_statistics_after_placeholders():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    render = panel.split('}else if(active_view=="MEMORIA"){', 1)[1].split('}else if(active_view=="LAB"){', 1)[0]
    assert render.index('"INFO4"),"Estatisticas: /api/statistics"') < render.index("if(refresh_data) RefreshSecondary();")
    assert 'string rate=JsonValue(r,"win_rate");' in panel
    assert 'SetLabel(Obj("INFO4"),"Estatisticas: "+(total==""?"—":total)+" decisoes • Win rate "+(rate==""?"—":rate)+"%"' in panel
    assert 'if(active_nav=="N7")' in panel
    assert 'string periods=JsonObjectValue(r,"periods");' in panel
    assert 'string daily=JsonObjectValue(periods,"daily");' in panel
    assert 'string weekly=JsonObjectValue(periods,"weekly");' in panel
    assert 'string monthly=JsonObjectValue(periods,"monthly");' in panel


def test_mql5_memory_label_does_not_invent_total_from_limited_records_endpoint():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    secondary = panel.split("void RefreshSecondary()", 1)[1].split("void SaveConfig()", 1)[0]
    assert '"/api/memory?limit=1"' in secondary
    assert '"Memoria: resposta recebida do runtime"' in secondary
    assert '"disponiveis"' not in secondary
    memory_block = secondary.split('if(Http("GET","/api/memory?limit=1","",r,code)){', 1)[1]
    memory_block = memory_block.split('}else SetLabel(Obj("INFO3")', 1)[0]
    assert 'JsonValue(r,"total")' not in memory_block
    assert 'JsonValue(r,"count")' not in memory_block


def test_mql5_cycle_status_does_not_mislabel_execution_acceptance_as_authorization():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    cycle = panel.split("void RunCycle()", 1)[1].split("void CloseCycle()", 1)[0]
    assert "execucao aceita=" in cycle
    assert "autorizado=" not in cycle
    assert 'allowed=="true"?' in cycle


def test_mql5_close_cycle_requires_runtime_closed_true_before_clearing_identity():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    close = panel.split("void CloseCycle()", 1)[1].split("int OnInit()", 1)[0]
    assert 'string closed=JsonValue(r,"closed");' in close
    assert 'if(closed=="true")' in close
    assert 'last_cycle_id=""; last_external_id="";' in close
    assert close.index('if(closed=="true")') < close.index('last_cycle_id=""; last_external_id="";')
    assert "Fechamento nao confirmado" in close
    assert "Fechamento DEMO confirmado" in close


def test_mql5_learning_view_is_named_estudo_in_user_facing_copy():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    assert '"ESTUDO • aprendizado separado da autorizacao operacional"' in panel
    assert '"ATUALIZAR ESTUDO"' in panel
    assert '"Estudo: "' in panel
    assert 'active_view=="ENSINO"' in panel  # Internal routing remains stable.


def test_mql5_panel_has_vertical_navigation_for_requested_modules():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    for label in ("COCKPIT", "ANALISE", "ESTUDO", "LABORATORIO", "REPLAY", "MEMORIA", "WIN/LOSS", "ALAVANCAGEM", "CONFIGURACOES"):
        assert label in panel
    for nav in range(1, 10):
        assert f'Obj("N{nav}")' in panel
    assert 'if(sparam==Obj("N1"))' in panel
    assert 'else if(sparam==Obj("N9"))' in panel
    assert 'active_view="REPLAY"' in panel
    assert 'active_view="ALAVANCAGEM"' in panel


def test_mql5_replay_and_leverage_are_not_misrepresented_as_native_integrations():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    assert "REPLAY • ligacao nativa ainda nao confirmada" in panel
    assert "Replay nao tem tela nativa ligada neste EA." in panel
    assert "ALAVANCAGEM • modulo web nao ligado ao EA nativo" in panel
    assert "Integracao nativa nao confirmada." in panel
    assert "Execucao autorizada: false." in panel
    assert "REAL: BLOQUEADO" in panel
    assert 'active_nav=="N7"?"WIN/LOSS • resultados, estatisticas e auditoria":"MEMORIA • historico, WIN/LOSS, estatisticas e auditoria"' in panel


def test_mql5_laboratory_does_not_claim_unverified_replay_endpoint():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    assert 'Replay: endpoint nativo ainda nao validado' in panel
    assert 'Replay: endpoint /api/replay disponivel no runtime' not in panel


def test_mql5_navigation_selection_and_layout_refresh_after_chart_change():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    render = panel.split("void RenderView(bool refresh_data=true)", 1)[1].split("void RefreshHealth()", 1)[0]
    event = panel.split("void OnChartEvent(", 1)[1]
    assert "RefreshNavigation();" in render
    assert "if(id==CHARTEVENT_CHART_CHANGE)" in event
    assert "if(panel_visible){ Panel(); RenderView(false); }" in event
    assert "RefreshPanelToggle();" in event
    assert "ApplyWatermark();" in event


def test_mql5_navigation_dispatch_has_no_duplicated_else_tokens():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    assert "else else if" not in panel
    for nav in range(1, 10):
        assert f'sparam==Obj("N{nav}")' in panel


def test_mql5_vertical_navigation_highlights_the_selected_module():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    assert 'string active_nav="N1";' in panel
    assert "void RefreshNavigation()" in panel
    assert 'OBJPROP_BGCOLOR,selected?C\'14,73,96\':C\'24,32,44\'' in panel
    assert 'OBJPROP_BORDER_COLOR,selected?C\'38,210,242\':C\'55,72,92\'' in panel
    for nav in range(1, 10):
        assert f'active_nav="N{nav}"' in panel
    assert panel.index("RefreshNavigation();", panel.index("void Panel()")) < panel.index("void DeletePanel(")

def test_mql5_memory_refresh_button_survives_view_cleanup_and_does_not_save_preferences():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    render = panel.split("void RenderView(bool refresh_data=true)", 1)[1].split("void RefreshHealth()", 1)[0]
    event = panel.split("void OnChartEvent(", 1)[1]
    assert 'SetButton(Obj("SAVE"),"ATUALIZAR ESTAT.",180,320,110,28);' in render
    assert 'if(active_view!="CONFIG" && active_view!="MEMORIA")' in render
    assert 'if(active_view=="MEMORIA") RefreshSecondary();' in event
    assert 'else if(active_view=="CONFIG") SaveConfig();' in event



def test_mql5_demo_cycle_fails_closed_without_explicit_confirmation_and_filter_checks():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    cycle = panel.split("void RunCycle()", 1)[1].split("void CloseCycle()", 1)[0]
    assert "no explicit closed-candle confirmation or filter checklist UI" in cycle
    assert '\\"confirmed\\":false' in cycle
    assert '\\"filters_ok\\":false' in cycle
    assert '\\"confirmed\\":true' not in cycle
    assert '\\"filters_ok\\":true' not in cycle


def test_mql5_replay_informational_view_removes_cycle_close_and_save_buttons():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    replay = panel.split('}else if(active_view=="REPLAY"){', 1)[1].split('}else if(active_view=="ALAVANCAGEM"){', 1)[0]
    assert 'if(ObjectFind(0,Obj("CYCLE"))>=0) ObjectDelete(0,Obj("CYCLE"));' in replay
    assert 'if(ObjectFind(0,Obj("CLOSE"))>=0) ObjectDelete(0,Obj("CLOSE"));' in replay
    assert 'if(ObjectFind(0,Obj("SAVE"))>=0) ObjectDelete(0,Obj("SAVE"));' in replay


def test_mql5_chart_resize_rerenders_layout_without_requerying_runtime():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    render = panel.split("void RenderView(bool refresh_data=true)", 1)[1].split("void RefreshHealth()", 1)[0]
    event = panel.split("void OnChartEvent(", 1)[1]
    assert "if(refresh_data) RefreshSecondary();" in render
    assert "if(refresh_data) Analyze();" in render
    assert "if(refresh_data){ RefreshHealth(); RefreshSecondary(); }" in render
    assert "if(refresh_data) RefreshLearning();" in render
    assert "if(refresh_data) RefreshNotifications();" in render
    assert "if(refresh_data) RefreshPreferences();" in render
    assert "if(panel_visible){ Panel(); RenderView(false); }" in event


def test_mql5_market_asset_count_uses_api_count_contract():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    assets = panel.split("void RefreshMarketAssets()", 1)[1].split("void RefreshSecondary()", 1)[0]
    assert 'string total=JsonValue(r,"count");' in assets
    assert 'string source=JsonValue(r,"source");' in assets
    assert 'StringFind(r,"\\\"symbol\\\":",p)' not in assets
    assert 'if(total=="") total="—";' in assets


def test_mql5_json_value_accepts_standard_json_whitespace_around_keys():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    parser = panel.split("string JsonValue(string json,string key)", 1)[1].split("bool Http(", 1)[0]
    assert "StringGetCharacter(json,p)!=':'" in parser
    assert "StringGetCharacter(json,p)=='\\t'" in parser
    assert "StringGetCharacter(json,p)==' ' || StringGetCharacter(json,p)=='\\n'" in parser


def test_mql5_win_loss_view_shows_real_outcomes_and_daily_weekly_monthly_hit_rates():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    secondary = panel.split("void RefreshSecondary()", 1)[1].split("void SaveConfig()", 1)[0]
    assert "string JsonObjectValue(string json,string key)" in panel
    assert 'string daily=JsonObjectValue(r,"daily");' in secondary
    assert 'string weekly=JsonObjectValue(r,"weekly");' in secondary
    assert 'string monthly=JsonObjectValue(r,"monthly");' in secondary
    assert 'JsonValue(r,"wins")' in secondary
    assert 'JsonValue(r,"losses")' in secondary
    assert '"Resultados fechados: "+(wins==""?"—":wins)+" WIN / "+(losses==""?"—":losses)+" LOSS"' in secondary
    assert '"Dia "+(d_rate==""?"—":d_rate)+"% ("+(d_total==""?"—":d_total)+") | Sem "' in secondary
    assert 'if(active_nav=="N7")' in secondary
    assert "rentabilidade" not in secondary.lower()
