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


def test_mql5_preview_compile_isolated_from_installed_ea():
    preview = (ROOT / "deployment" / "compile_mql5_panel_preview.ps1").read_text(encoding="utf-8")
    assert "MQL5\\Experts\\ControladorTradingPreview" in preview
    assert "$previewSource = Join-Path $previewDir 'Controlador-Trading-Preview.mq5'" in preview
    assert '& $MetaEditorPath "/compile:$previewSource" "/log:$log"' in preview
    assert "installed_ea_replaced = $false" in preview
    assert "real_execution_authorized = $false" in preview
    assert "0 erros, 0 avisos" in preview
    assert "Copy-Item -LiteralPath $source -Destination $previewSource -Force" in preview
    assert 'Remove-Item -LiteralPath $previewBinary -Force' in preview
    assert 'Copy-Item -LiteralPath $previewBinary -Destination "$previewBinary.$stamp.bak" -Force' in preview
    assert "Join-Path $Mt5DataPath 'MQL5\\Experts\\ControladorTrading'" not in preview


def test_mql5_panel_has_single_repository_source():
    panel = ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5"
    legacy = ROOT / "mql5" / "Experts" / "ControladorTrading" / "ControladorTradingPanel.mq5"
    assert panel.is_file()
    assert not legacy.exists()


def test_controller_startup_never_syncs_or_compiles_the_installed_ea():
    startup = (ROOT / "deployment" / "start_controlador_runtime.ps1").read_text(encoding="utf-8")
    sync_script = (ROOT / "deployment" / "sync_mql5_panel.ps1").read_text(encoding="utf-8")
    assert "Sync-Mt5Panel" not in startup
    assert "sync_mql5_panel.ps1" not in startup
    installer = (ROOT / "deployment" / "install_windows_autostart.ps1").read_text(encoding="utf-8")
    assert "$syncScript" not in installer
    assert "ação manual separada" in installer
    # Keep the explicit maintenance utility available, but outside runtime startup.
    assert '& $MetaEditorPath "/compile:$destination"' in sync_script
    assert "Copy-WithRetry -Source $source -Destination $destination" in sync_script


def test_mql5_panel_primes_runtime_and_refreshes_market_data_on_new_bars():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    init = panel.split("int OnInit()", 1)[1].split("int OnDeinit", 1)[0]
    timer = panel.split("void OnTimer()", 1)[1].split("void OnChartEvent", 1)[0]
    analyze = panel.split("void Analyze(bool render=true)", 1)[1].split("void RunCycle()", 1)[0]
    assert "Analyze(panel_visible);" in init
    assert "last_analysis_bar=iTime(_Symbol,_Period,0);" in init
    assert "current_bar!=last_analysis_bar" in timer
    assert 'if(active_view=="COCKPIT" || active_view=="ANALISE")' in timer
    assert "Analyze(new_bar);" in timer
    assert "Analyze(new_bar && (active_view==\"COCKPIT\" || active_view==\"ANALISE\"));" not in timer
    assert "Analyze(false);" in timer
    assert '"/api/runtime/analysis/local"' in analyze
    assert "if(!render) return;" in analyze


def test_mql5_compact_signal_fails_closed_on_health_loss_and_refreshes_each_tick():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    health = panel.split("void RefreshHealth()", 1)[1].split("void RefreshSecondary()", 1)[0]
    analyze = panel.split("void Analyze(bool render=true)", 1)[1].split("void RunCycle()", 1)[0]
    init = panel.split("int OnInit()", 1)[1].split("void OnDeinit", 1)[0]
    timer = panel.split("void OnTimer()", 1)[1].split("void OnChartEvent", 1)[0]

    assert "bool health_ok=false;" in panel
    assert "health_ok=false;" in health
    assert 'UpdateCompactSignal("INDISPONIVEL","",false);' in health
    assert "health_ok=true;" in health
    assert "if(!health_ok)" in analyze
    assert 'UpdateCompactSignal("INDISPONIVEL","",false);' in analyze
    assert "RefreshHealth();" in init
    assert "RefreshHealth();" in timer
    assert "Analyze(false);" in timer
    assert 'if(active_view=="COCKPIT" || active_view=="ANALISE")' in timer
    assert "Analyze(new_bar);" in timer
    assert "Analyze(new_bar && (active_view==\"COCKPIT\" || active_view==\"ANALISE\"));" not in timer


def test_mql5_panel_uses_approved_compact_c_signal_without_watermark():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    assert '"Controlador Trading"' in panel
    assert '"ECOSSISTEMA • MT5 • DEMO / SIMULACAO"' in panel
    assert "RUNTIME REAL" not in panel
    assert "InpPanelWidth = 360" in panel
    assert "InpPanelHeight = 500" in panel
    assert "bool panel_visible=false" in panel
    assert 'SetCompactLabel(Obj("PANEL_TOGGLE_BG"),"●"' in panel
    assert 'SetCompactLabel(Obj("PANEL_TOGGLE"),"C"' in panel
    assert 'return "↑ COMPRAR";' in panel
    assert 'return "↓ VENDER";' in panel
    assert 'JsonObjectValue(r,"quality","score")' in panel
    assert "UpdateCompactSignal(signal,score,true)" in panel
    assert "watermark" not in panel.lower()
    assert "WATERMARK" not in panel

    visible_labels = "\\n".join(line for line in panel.splitlines() if "SetLabel(" in line or "SetButton(" in line)
    assert '"ANALISAR NO RUNTIME"' not in visible_labels
    assert '"/api/memory"' not in visible_labels
    assert '"/api/statistics"' not in visible_labels
    assert "learning_authorizes_trading=false" not in visible_labels
    assert "Execution Gate" not in visible_labels
    assert "Motor de decisao:" not in visible_labels

def test_mql5_config_mode_and_leverage_controls_persist_without_real_authority():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    prefs = panel.split("void RefreshPreferences()", 1)[1].split("void RefreshNotifications()", 1)[0]
    save = panel.split("void SaveConfig()", 1)[1].split("void Analyze(bool render=true)", 1)[0]
    events = panel.split("void OnChartEvent", 1)[1]

    assert 'Obj("MODE_TOGGLE")' not in prefs
    assert 'Obj("MODE_TOGGLE")' not in events
    assert 'Obj("LEVERAGE_TOGGLE")' in prefs
    assert '"ALAVANCAGEM: ON"' in prefs
    assert '"ALAVANCAGEM: OFF"' in prefs
    assert 'selected_mode="DEMO";' in prefs
    assert r'\"selected_mode\":\"DEMO\"' in save
    assert "leverage_enabled=!leverage_enabled" in events
    assert "leverage_enabled" in save
    assert 'SetLabel(Obj("INFO5"),"REAL: BLOQUEADO' in prefs

def test_mql5_sync_script_has_single_retry_helper_definition():
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.count("function Copy-WithRetry") == 1
    assert text.count("function Restore-File") == 1


def test_controller_supervisor_requires_health_before_healthy():
    startup = (ROOT / "deployment" / "start_controlador_runtime.ps1").read_text(encoding="utf-8")
    assert "Test-ControllerHealth" in startup
    assert "Wait-ControllerHealth" in startup
    assert "Write-SupervisorStatus 'STARTING'" in startup
    assert "Write-SupervisorStatus 'HEALTHY' 'app.py ativo; liveness e health detalhado confirmados; REAL bloqueado.'" in startup
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

def test_mql5_panel_hide_preserves_compact_c_signal_and_deinit_removes_all_objects():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    delete = panel.split("void DeletePanel(", 1)[1].split("string JsonValue", 1)[0]
    toggle = panel.split("void TogglePanel()", 1)[1].split("void LoadPanelVisibility", 1)[0]
    deinit = panel.split("void OnDeinit(", 1)[1].split("void OnTimer()", 1)[0]

    assert "bool preserveCompact=false" in delete
    assert 'n==Obj("PANEL_TOGGLE_BG")' in delete
    assert 'n==Obj("COMPACT_SIGNAL")' in delete
    assert 'n==Obj("COMPACT_SCORE")' in delete
    assert "if(preserveCompact) RefreshPanelToggle();" in delete
    assert "else DeletePanel(true);" in toggle
    assert "DeletePanel();" in deinit
    assert "watermark" not in panel.lower()

def test_mql5_panel_toggle_tracks_fixed_lower_chart_position():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    render = panel.split("void Panel()", 1)[1].split("void RenderView()", 1)[0]
    timer = panel.split("void OnTimer()", 1)[1].split("void OnChartEvent", 1)[0]
    visible_timer = timer.split("   RefreshPanelLayout();", 1)[1]
    assert render.index("RefreshPanelLayout();") < render.index("RefreshPanelToggle();")
    assert visible_timer.lstrip().startswith("RefreshPanelToggle();")
    assert "int cy=MathMax(42,ch-46);" in panel
    assert 'SetCompactLabel(Obj("PANEL_TOGGLE"),"C"' in panel
    assert 'SetCompactLabel(Obj("COMPACT_SIGNAL")' in panel

def test_mql5_sync_requires_matching_source_and_binary_provenance_to_skip_compilation():
    text = SCRIPT.read_text(encoding="utf-8")
    assert '$provenance = "$binary.provenance.json"' in text
    assert "recordedProvenance.source_sha256" in text
    assert "recordedProvenance.binary_sha256" in text
    assert "if (-not $Force -and $sourceHash -eq $destinationHash -and $binaryUsable)" in text
    assert "source_sha256 = $sourceHash" in text
    assert "binary_sha256 = $binaryHashAfter" in text
    assert "Set-Content -LiteralPath $provenanceTemp -Encoding ASCII" in text
    assert text.count("Restore-File -Backup $backupProvenance -Target $provenance") >= 7
    assert text.index("if ($binaryWriteTime -lt $compileStartedAt.AddSeconds(-2))") < text.index("binary_sha256 = $binaryHashAfter")


def test_mql5_close_preserves_cycle_until_broker_confirms_position_closed():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    close = panel.split("void CloseCycle()", 1)[1].split("int OnInit()", 1)[0]
    assert 'JsonValue(r,"closed")=="true"' in close
    assert '"/api/runtime/close/local/reconcile"' in close
    assert 'JsonObjectValue(reconciliation,"close_reconciliation","state")' in close
    assert 'state=="CLOSED"' in close
    assert 'state=="OPEN"' in close
    assert close.count("ClearCycleIdentity();") >= 2
    assert "Fechamento inconclusivo; ciclo preservado." in close
    assert "Sem saida temporizada; fechamento manual explicito." in panel


def test_mql5_preserves_active_cycle_ticket_across_analysis_and_ea_restart():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    run_cycle = panel.split("void RunCycle()", 1)[1].split("void CloseCycle()", 1)[0]
    init = panel.split("int OnInit()", 1)[1].split("void OnDeinit", 1)[0]
    assert "LoadCycleIdentity();" in init
    assert "PersistCycleIdentity();" in run_cycle
    assert "ClearCycleIdentity();" in panel
    assert "FileOpen(CycleIdentityFileName(),FILE_WRITE|FILE_TXT|FILE_ANSI)" in panel
    assert "FileOpen(CycleIdentityFileName(),FILE_READ|FILE_TXT|FILE_ANSI)" in panel
    assert 'if(allowed=="true" && accepted=="true" && cid!="" && eid!="")' in run_cycle
    assert "last_cycle_id=cid; last_external_id=eid;" not in run_cycle
    assert 'if(last_cycle_id!="" && last_external_id!="" && !RefreshActiveCycleState())' in run_cycle
    assert "RefreshActiveCycleState()" in run_cycle
    refresh = panel.split("bool RefreshActiveCycleState()", 1)[1].split("void RunCycle()", 1)[0]
    assert 'JsonObjectValue(response,"close_reconciliation","state")' in refresh
    assert 'state=="CLOSED"' in refresh
    assert 'state=="OPEN"' in refresh
    assert "if(!cycle_identity_store_valid)" in run_cycle
    assert "FileIsExist(CycleIdentityFileName())" in panel
    assert "Falha ao salvar ticket; não reinicie EA." in run_cycle


def test_mql5_releases_stale_cycle_only_after_read_only_broker_confirmation():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    refresh = panel.split("bool RefreshActiveCycleState()", 1)[1].split("void RunCycle()", 1)[0]
    run_cycle = panel.split("void RunCycle()", 1)[1].split("void CloseCycle()", 1)[0]
    assert 'Http("POST","/api/runtime/close/local/reconcile"' in refresh
    assert 'state=="CLOSED"' in refresh
    assert "ClearCycleIdentity();" in refresh
    assert 'state=="OPEN"' in refresh
    assert 'if(last_cycle_id!="" && last_external_id!="" && !RefreshActiveCycleState())' in run_cycle
    assert 'JsonObjectValue(r,"timed_exit","scheduled")' in run_cycle
    assert 'JsonObjectValue(r,"timed_exit","due_at")' in run_cycle
    assert "best-effort" in run_cycle



def test_mql5_native_recovery_inventory_supports_multiple_exact_tickets():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    parser = panel.split("bool ExtractJsonArrayObjects", 1)[1].split("bool RefreshRecoveryInventory", 1)[0]
    selection = panel.split("void ReconcileSelectedRecovery()", 1)[1].split("int OnInit()", 1)[0]
    events = panel.split("void OnChartEvent", 1)[1]

    assert 'Http("GET","/api/runtime/positions/recovery/local"' in panel
    assert 'ExtractJsonArrayObjects(json,"positions",objects)' in panel
    assert "RecoveryPosition recovery_items[];" in panel
    assert "bool ParseRecoveryInventory(string json)" in panel
    assert "bool RefreshRecoveryInventory()" in panel
    assert "void ReconcileSelectedRecovery()" in panel
    assert "void CloseSelectedRecovery()" in panel
    assert 'Http("GET","/api/runtime/positions/recovery/local"' in panel
    assert "recovery_items[n].cycle_id=cycle;" in panel
    assert "recovery_items[n].external_id=ticket;" in panel
    assert "if(c!='{') return false;" in parser
    assert "if(depth!=0 || inString) return false;" in parser
    assert "bool have_item=false,after_comma=false;" in parser
    assert "if(c==']') return !after_comma;" in parser
    assert 'state!="BLOCKED_ACCOUNT_IDENTITY"' in parser
    assert 'state!="BROKER_CONFIRMED_OPEN"' in parser
    assert 'state!="RECONCILIATION_REQUIRED"' in parser
    assert 'Http("POST","/api/runtime/close/local/reconcile"' in selection
    assert 'item.state!="BROKER_CONFIRMED_OPEN"' in selection
    assert "if(!recovery_close_armed)" in selection
    assert 'Http("POST","/api/runtime/close/local"' in selection
    assert 'Obj("REC_PREV")' in events
    assert 'Obj("REC_NEXT")' in events
    assert 'Obj("REC_RECONCILE")' in events
    assert 'Obj("REC_CLOSE")' in events


def test_mql5_json_helpers_accept_standard_json_whitespace_and_escaped_strings():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    helpers = panel.split("int JsonValueStart", 1)[1].split("bool Http(", 1)[0]

    assert "JsonValueStart(json,arrayKey)" in helpers
    assert "if(have_item && !after_comma) return false;" in helpers
    assert "JsonValueStart(json,objectKey)" in helpers
    assert "StringGetCharacter(json,q)=='\\n'" in helpers
    assert "StringGetCharacter(json,q)=='\\t'" in helpers
    assert "if(escaped) escaped=false;" in helpers
    assert r"else if(c=='\\') escaped=true;" in helpers
    assert r"else if(ch=='\\') escaped=true;" in helpers


def test_mql5_sync_backup_creation_fails_closed_before_any_destination_write():
    text = SCRIPT.read_text(encoding="utf-8")
    backup_start = text.index("$backupSource =")
    destination_write = text.index(
        "Copy-WithRetry -Source $source -Destination $destination", backup_start
    )
    backup_phase = text[backup_start:destination_write]
    assert "try {" in backup_phase
    assert "Copy-WithRetry -Source $destination -Destination $backupSource" in backup_phase
    assert "Copy-WithRetry -Source $binary -Destination $backupBinary" in backup_phase
    assert "Copy-WithRetry -Source $provenance -Destination $backupProvenance" in backup_phase
    assert "Copy-WithRetry -Source $log -Destination $backupLog" in backup_phase
    assert "catch {" in backup_phase
    assert "o destino do EA ainda não foi modificado" in backup_phase
    assert "Restore-File" not in backup_phase
    assert text.index("Falha ao criar os backups dos artefatos") < text.index(
        "Copy-WithRetry -Source $source -Destination $destination"
    )

def test_mql5_sync_refuses_to_overwrite_preexisting_backup_artifacts():
    text = SCRIPT.read_text(encoding="utf-8")
    backup_start = text.index("$backupSource =")
    backup_try = text.index("try {", backup_start)
    collision_guard = text.index("$backupCollision =", backup_start)
    directory_create = text.index("New-Item -ItemType Directory -Force -Path $destinationDir")
    assert backup_start < collision_guard < directory_create < backup_try
    assert "$stamp = (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N')" in text
    assert "$backupTargets = @($backupSource, $backupBinary, $backupProvenance, $backupLog)" in text
    assert "Test-Path -LiteralPath $_" in text[collision_guard:directory_create]
    assert "Backup com nome já existente" in text[collision_guard:directory_create]
    assert "nenhum artefato do EA foi alterado" in text[collision_guard:directory_create]


def test_mql5_sync_whatif_never_initializes_python_terminal_bridge_without_resolved_data_path():
    text = SCRIPT.read_text(encoding="utf-8")
    resolver = text.split("function Resolve-Mt5DataPath", 1)[1].split("\n$dataPath =", 1)[0]
    guard = resolver.index("if ($WhatIfPreference)")
    bridge = resolver.index("$paths = Get-Mt5Paths -TerminalPath $TerminalPath")
    assert guard < bridge
    assert "Simulação -WhatIf não inicializa nem consulta o terminal MT5" in resolver
    assert "Informe -Mt5DataPath ou CONTROLADOR_MT5_DATA_PATH" in resolver
    assert "Get-Mt5Paths -TerminalPath $TerminalPath" in resolver[bridge:]

    terminal_resolver = text.split("function Resolve-Mt5TerminalPath", 1)[1].split("$Mt5TerminalPath =", 1)[0]
    terminal_whatif = terminal_resolver.index("if ($WhatIfPreference)")
    terminal_process_query = terminal_resolver.index("Get-CimInstance Win32_Process")
    assert terminal_whatif < terminal_process_query
    assert "a simulação não consulta processos do MT5" in terminal_resolver
