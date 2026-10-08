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
        "MetaEditor terminou com código de saída",
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


def test_mql5_panel_uses_controlador_trading_brand_and_watermark_toggle():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    assert '"Controlador-Trading"' in panel
    assert '"CONTROLADOR TRADING"' in panel
    assert '"WATERMARK_MARK"' in panel
    assert "ObjectSetDouble(0,mark,OBJPROP_ANGLE,18.0)" in panel
    assert "ObjectSetDouble(0,name,OBJPROP_ANGLE,18.0)" in panel
    assert "InpPanelWidth = 320" in panel
    assert "InpPanelHeight = 420" in panel
    assert "panel_x=12;" in panel
    assert "MathRound(cw*0.25)" in panel
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
    assert "if(!panel_visible){ RefreshPanelToggle(); return; }" in panel
    assert "execution" not in "TogglePanel" or "runtime" not in "TogglePanel"


def test_mql5_panel_off_does_not_render_on_init():
    panel = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")
    init = panel.split("int OnInit()", 1)[1].split("int OnDeinit", 1)[0]
    assert "if(panel_visible){" in init
    assert "Panel();" in init
    assert "RenderView();" in init
    assert "}else{" in init
    assert "RefreshPanelToggle();" in init
