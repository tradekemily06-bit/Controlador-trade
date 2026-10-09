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
        "scheduled-task:$task",
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
    assert "mt5.initialize(path=sys.argv[1])" in text
    assert "actual==expected" in text
    assert "$Mt5TerminalPath 2>$null" in text


def test_controller_health_gate_uses_current_safe_health_contract():
    text = _read("deployment/start_controlador_runtime.ps1")
    for required in (
        "$payload.execution_allowed -ne $false",
        "$payload.real -ne \"DESABILITADO\"",
        "$payload.operational_observability.execution",
        "$op.allowed -ne $false",
        "$op.real -ne \"DISABLED\"",
        "$payload.real_runtime",
        "$realRuntime.real_execution_allowed -ne $false",
        "$realRuntime.explicitly_enabled -ne $false",
    ):
        assert required in text
    assert '$payload.execution.allowed' not in text
    assert '$payload.execution.real' not in text



def test_controller_supervisor_pins_runtime_paths_and_demo_safety_environment():
    text = _read("deployment/start_controlador_runtime.ps1")
    for required in (
        "$env:CONTROLADOR_BIND_HOST = '127.0.0.1'",
        "$env:PORT = '8000'",
        "$env:CONTROLADOR_EXECUTION_PROVIDER = 'ic_markets_mt5_demo'",
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



def test_mt5_supervisor_pins_health_check_to_configured_terminal():
    text = _read("deployment/start_mt5_runtime.ps1")
    assert "mt5.initialize(path=sys.argv[1])" in text
    assert "configured_directory" in text
    assert "actual_directory == configured_directory" in text
    assert "& $PythonExe -c $healthCheckCode $Mt5TerminalPath" in text

def test_mt5_supervisor_only_tracks_process_matching_configured_executable():
    text = _read("deployment/start_mt5_runtime.ps1")
    assert "function Get-ConfiguredMt5Process" in text
    assert "Get-CimInstance Win32_Process" in text
    assert "[System.IO.Path]::GetFullPath($_.ExecutablePath)" in text
    assert "Get-ConfiguredMt5Process" in text
    assert "Get-Process -Name $processName" not in text
    assert "Fail closed: an unknown process state" in text
    assert "throw $message" in text



def test_mt5_supervisor_fails_closed_on_duplicate_configured_processes():
    text = _read("deployment/start_mt5_runtime.ps1")
    process_lookup = text.split("function Get-ConfiguredMt5Process {", 1)[1].split(
        "\nfunction Stop-Mt5Process", 1
    )[0]
    assert "$candidates.Count -gt 1" in process_lookup
    assert "estado ambíguo" in process_lookup
    assert "$candidates.Count -eq 0" in process_lookup
    assert "Select-Object -First 1" not in process_lookup


def test_mt5_supervisor_fails_closed_when_restart_history_is_corrupt():
    text = _read("deployment/start_mt5_runtime.ps1")
        loader = text.split("function Load-RestartHistory {", 1)[1].split(
            "function Save-RestartHistory", 1
        )[0]
    assert "ConvertFrom-Json" in loader
    assert "Histórico de reinícios inválido" in loader
    assert "throw $message" in loader
    assert "$restartTimes.Clear()" in loader
    assert loader.index("throw $message") > loader.index("Histórico de reinícios inválido")
    assert "Write-SupervisorStatus 'FAILED' 'RESTART_HISTORY_INVALID'" in loader
    assert text.index("function Write-SupervisorStatus") < text.index("\nLoad-RestartHistory\n")


def test_portability_scripts_pass_paths_as_arguments_and_keep_restore_safe_by_default():
    backup = _read("deployment/backup_runtime.ps1")
    restore = _read("deployment/restore_runtime.ps1")
    assert "create_backup(sys.argv[1], sys.argv[2])" in backup
    assert "r'$RuntimeDir'" not in backup
    assert "[switch]$Replace" in restore
    assert "restore_backup(sys.argv[1], sys.argv[2], replace=(sys.argv[3] == 'true'))" in restore
    assert "r'$BackupFile'" not in restore

def test_controller_supervisor_fails_closed_when_restart_history_is_corrupt():
    text = _read("deployment/start_controlador_runtime.ps1")
    loader = text.split("function Load-RestartHistory {", 1)[1].split(
        "\nfunction Save-RestartHistory", 1
    )[0]
    assert "ConvertFrom-Json" in loader
    assert "Histórico de reinícios inválido" in loader
    assert "Write-SupervisorStatus 'FAILED' 'RESTART_HISTORY_INVALID'" in loader
    assert "throw $message" in loader
    assert "$restartTimes.Clear()" in loader
    assert text.index("function Write-SupervisorStatus") < text.index("\nLoad-RestartHistory\n")

def test_controller_supervisor_fails_closed_on_ambiguous_process_discovery():
    text = _read("deployment/start_controlador_runtime.ps1")
    assert "Get-CimInstance Win32_Process -ErrorAction Stop" in text
    assert "$existingControllers.Count -gt 1" in text
    assert "PROCESS_DISCOVERY_FAILED" in text
    assert "DUPLICATE_CONTROLLER_PROCESSES" in text
    assert "Select-Object -First 1" not in text



def test_restart_history_rejects_json_scalars_and_non_string_entries():
    for name in (
        "deployment/start_controlador_runtime.ps1",
        "deployment/start_mt5_runtime.ps1",
    ):
        text = _read(name)
        loader = text.split("function Load-RestartHistory {", 1)[1].split(
            "\\nfunction Save-RestartHistory", 1
        )[0]
        assert "$raw = Get-Content -LiteralPath $restartHistoryPath -Raw -ErrorAction Stop" in loader
        assert "$raw.Trim() -notmatch '(?s)^\\[.*\\]$'" in loader
        assert "$item -isnot [string]" in loader
        assert "RESTART_HISTORY_INVALID" in loader
        assert "throw $message" in loader
