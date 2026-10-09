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
    assert '"Controlador-Trading"' in panel
    assert '"CONTROLADOR TRADING"' in panel
    assert '"WATERMARK_MARK"' in panel
    assert "ObjectSetInteger(0,mark,OBJPROP_FONTSIZE,30)" in panel
    assert "ObjectSetInteger(0,name,OBJPROP_FONTSIZE,18)" in panel
    assert "InpPanelWidth = 280" in panel
    assert "InpPanelHeight = 380" in panel
    assert "panel_x=MathMax(12,cw-panel_width-12);" in panel
    assert "MathRound(cw*0.22)" in panel
    assert "OBJPROP_ANGLE,18.0" not in panel
    assert "ToggleWatermark" in panel
    assert "GlobalVariableSet(WatermarkKey()" in panel


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

def test_mql5_sync_fails_closed_when_target_terminal_instance_is_ambiguous():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "function Resolve-Mt5TerminalPath" in text
    assert "Get-CimInstance Win32_Process" in text
    assert "Mais de uma instância corresponde ao MT5 configurado" in text
    assert "$Mt5TerminalPath = Resolve-Mt5TerminalPath -RequestedPath $Mt5TerminalPath" in text
    assert "sincronização cancelada para não atualizar a pasta de dados errada" in text



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


