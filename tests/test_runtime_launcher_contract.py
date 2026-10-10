from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_runtime_launchers_resolve_python_and_fail_closed():
    for name in (
        "deployment/start_controlador_runtime.ps1",
        "deployment/start_mt5_runtime.ps1",
        "deployment/bootstrap_windows_runtime.ps1",
        "deployment/backup_runtime.ps1",
        "deployment/restore_runtime.ps1",
    ):
        text = _read(name)
        assert "Get-Command $PythonExe" in text
        assert "Python não encontrado" in text
        assert "Test-Path -LiteralPath $PythonExe -PathType Leaf" in text


def test_bootstrap_stops_after_dependency_install_failure():
    text = _read("deployment/bootstrap_windows_runtime.ps1")
    assert "$LASTEXITCODE -ne 0" in text
    assert "Falha ao instalar requirements.txt." in text
    assert "Falha ao instalar requirements-mt5.txt." in text
    assert "MetaTrader5 não pôde ser importado" in text


def test_read_only_windows_validator_covers_deployment_surface():
    text = _read("deployment/validate_windows_runtime.ps1")
    for required in (
        "controller-health-safe",
        "mt5-demo-health",
        "market-data-candles-read-only",
        "mt5.copy_rates_from_pos('EURUSD',mt5.TIMEFRAME_M5,1,100)",
        "$candleCount -gt 0",
        "MT5_DEMO_MARKET=True",
        "orders=not requested",
        "scheduled-task:$task",
        "scheduled-task-enabled:$task",
        "scheduled-task-running:$task",
        "mql5-source",
        "mql5-ex5-current",
        "$payload.execution_allowed -eq $false",
        "$payload.real -eq 'DESABILITADO'",
        "$op.allowed -eq $false",
        "$op.real -eq 'DISABLED'",
        "$realRuntime.real_execution_allowed -eq $false",
        "$realRuntime.explicitly_enabled -eq $false",
        "exit 2",
    ):
        assert required in text
    assert "$payload.execution.allowed" not in text
    assert "$payload.execution.real" not in text
    assert "Register-ScheduledTask" not in text
    assert "Start-Process" not in text
    assert "mt5.initialize(path=p, timeout=15000)" in text
    assert "mt5-supervisor-status.json" in text
    assert "controlador-supervisor-status.json" in text
    assert "$status.state -eq 'HEALTHY'" in text
    assert "$Mt5TerminalPath | Out-Null" in text
    assert "Invoke-WebRequest -UseBasicParsing -Method Post" not in text
    assert "/api/runtime/analysis" not in text
    assert "copy_rates_from_pos" in text


def test_controller_health_gate_uses_current_safe_health_contract():
    text = _read("deployment/start_controlador_runtime.ps1")
    for required in (
        "$payload.execution_allowed -ne $false",
        '$payload.real -ne "DESABILITADO"',
        "$payload.operational_observability.execution",
        "$op.allowed -ne $false",
        '$op.real -ne "DISABLED"',
        "$payload.real_runtime",
        "$realRuntime.real_execution_allowed -ne $false",
        "$realRuntime.explicitly_enabled -ne $false",
    ):
        assert required in text
    assert "$payload.execution.allowed" not in text
    assert "$payload.execution.real" not in text


def test_controller_supervisor_pins_runtime_paths_and_demo_safety_environment():
    text = _read("deployment/start_controlador_runtime.ps1")
    for required in (
        "$env:CONTROLADOR_BIND_HOST = '127.0.0.1'",
        "$env:PORT = '8000'",
        "$env:CONTROLADOR_EXECUTION_PROVIDER = 'ic_markets_mt5_demo'",
        "$env:CONTROLADOR_MT5_TERMINAL_PATH = $Mt5TerminalPath",
        "$env:CONTROLADOR_RUNTIME_DIR = $RuntimeDir",
        "$env:CONTROLADOR_SECURITY_AUDIT_DB = Join-Path $RuntimeDir 'security-audit.sqlite'",
        "$env:CONTROLADOR_REMOTE_ACCESS_REQUIRED = 'true'",
        "$env:CONTROLADOR_LOCAL_MUTATIONS_ALLOWED = 'true'",
        "$env:CONTROLADOR_REAL_EXPLICITLY_ENABLED = 'false'",
        "$env:CONTROLADOR_REAL_EXECUTION_ALLOWED = 'false'",
        "$env:CONTROLADOR_REAL_AUDIT_VERIFIED = 'false'",
        "$env:CONTROLADOR_REAL_RISK_APPROVED = 'false'",
        "$env:CONTROLADOR_REAL_AUTHORIZATION_ID = ''",
        "$env:CONTROLADOR_REAL_AUDIT_ID = ''",
        "$env:CONTROLADOR_REAL_ADMISSION_ID = ''",
    ):
        assert required in text


def test_mt5_supervisor_logs_specific_health_gate_failure_reason():
    text = _read("deployment/start_mt5_runtime.ps1")
    assert "MT5_HEALTH_DIAGNOSTIC=" in text
    assert "last_error" in text
    assert "terminal_connected" in text
    assert "configured_terminal_path_mismatch" in text
    assert "account_not_confirmed_demo" in text
    assert "$script:LastMt5HealthDiagnostic" in text
    assert "Diagnóstico do health gate MT5" in text


def test_mt5_supervisor_pins_health_and_process_management_to_configured_terminal():
    text = _read("deployment/start_mt5_runtime.ps1")
    assert "mt5.initialize(path=path, timeout=15000)" in text
    assert "$Mt5TerminalPath" in text
    assert "function Get-ConfiguredMt5Process" in text
    assert "Mais de uma instância corresponde" in text
    assert "function Get-Mt5AccountSafetyState" in text
    assert "$accountSafetyState -ne 'DEMO'" in text
    assert "Get-Process -Name $processName" not in text


def test_controller_supervisor_and_installer_share_configured_mt5_terminal():
    controller = _read("deployment/start_controlador_runtime.ps1")
    installer = _read("deployment/install_windows_autostart.ps1")
    assert "$env:CONTROLADOR_MT5_TERMINAL_PATH = $Mt5TerminalPath" in controller
    bootstrap = _read("deployment/bootstrap_windows_runtime.ps1")
    assert "CONTROLADOR_MT5_TERMINAL_PATH = $Mt5TerminalPath" in bootstrap
    assert "run_preflight(mt5, initialize_timeout_ms=15000)" in controller
    assert "-Mt5TerminalPath $Mt5TerminalPath" in controller
    assert "-Mt5TerminalPath \"' + $Mt5TerminalPath + '\"" in installer


def test_market_data_adapter_and_preflight_honor_configured_terminal():
    adapter = _read("execution/icmarkets_mt5_market_data.py")
    preflight = _read("execution/mt5_demo_runtime_preflight.py")
    assert "CONTROLADOR_MT5_TERMINAL_PATH" in adapter
    assert "mt5.initialize(path=self._terminal_path, timeout=15_000)" in adapter
    assert "CONTROLADOR_MT5_TERMINAL_PATH" in preflight
    assert "mt5.initialize(path=configured_path, timeout=initialize_timeout_ms)" in preflight

def test_controller_supervisor_preserves_mql5_sync_failure_details():
    text = _read("deployment/start_controlador_runtime.ps1")
    assert "$syncOutput = & powershell.exe" in text
    assert " -Mt5TerminalPath $Mt5TerminalPath 2>&1" in text
    assert "$syncExitCode = $LASTEXITCODE" in text
    assert 'Write-StartupLog "Sincronização MQL5: $message"' in text
    assert "terminou com código $syncExitCode" in text

def test_supervisors_reject_restart_history_that_is_future_dated_or_out_of_order():
    for name in (
        "deployment/start_controlador_runtime.ps1",
        "deployment/start_mt5_runtime.ps1",
    ):
        text = _read(name)
        assert "$futureLimit = (Get-Date).ToUniversalTime().AddMinutes(5)" in text
        assert "$parsedRestart -gt $futureLimit" in text
        assert "$parsedRestart -lt $previousRestart" in text
        assert "$json = ConvertTo-Json -InputObject @($values) -Depth 3" in text
        assert "RESTART_HISTORY_INVALID" in text
        assert "supervisor interrompido para preservar o limite de segurança" in text or "supervisor MT5 interrompido para preservar o limite de segurança" in text




def test_controller_supervisor_bounds_and_logs_mt5_preflight_failures():
    controller = _read("deployment/start_controlador_runtime.ps1")
    preflight = _read("execution/mt5_demo_runtime_preflight.py")
    assert "initialize_timeout_ms=15000" in controller
    assert "MT5_PREFLIGHT=" in controller
    assert "MT5 DEMO preflight tentativa" in controller
    assert "não foi confirmado dentro de" in controller
    assert "initialize_timeout_ms: int = 15_000" in preflight
    assert "terminal MT5 não conectado após initialize" in preflight
    assert "cotação ou limites de volume inválidos" in preflight



def test_execution_adapter_pins_and_bounds_mt5_initialization():
    adapter = _read("execution/icmarkets_mt5_demo_adapter.py")
    assert 'os.environ.get("CONTROLADOR_MT5_TERMINAL_PATH", "")' in adapter
    assert "mt5.initialize(path=configured_path, timeout=15_000)" in adapter
    assert "mt5.initialize(timeout=15_000)" in adapter
    assert "terminal MT5 conectado não corresponde ao caminho configurado" in adapter



def test_market_data_adapter_bounds_initialization_and_requires_connected_terminal():
    adapter = _read("execution/icmarkets_mt5_market_data.py")
    assert "mt5.initialize(path=self._terminal_path, timeout=15_000)" in adapter
    assert "mt5.initialize(timeout=15_000)" in adapter
    assert "terminal MT5 não conectado após initialize" in adapter
