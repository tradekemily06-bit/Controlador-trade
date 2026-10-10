param(
    [Parameter(Mandatory = $true)]
    [string]$Mt5TerminalPath,
    [string]$ProjectRoot = 'C:\Controlador-trade',
    [string]$PythonExe = 'python',
    [string]$RuntimeDir = '',
    [int]$RestartDelaySeconds = 10,
    [int]$MaxRestartsPerHour = 6,
    [int]$HealthWaitSeconds = 60,
    [int]$HealthPollSeconds = 5,
    [int]$HealthFailureThreshold = 3
)

$ErrorActionPreference = 'Stop'

if ($PythonExe -eq 'python' -or $PythonExe -eq 'python.exe') {
    $resolvedPython = Get-Command $PythonExe -ErrorAction SilentlyContinue
    if ($null -eq $resolvedPython -or [string]::IsNullOrWhiteSpace($resolvedPython.Source)) {
        throw "Python não foi encontrado no PATH. Informe -PythonExe com o caminho completo do python.exe."
    }
    $PythonExe = $resolvedPython.Source
}
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Python não encontrado: $PythonExe"
}
if ([string]::IsNullOrWhiteSpace($RuntimeDir)) {
    $RuntimeDir = Join-Path $ProjectRoot '.runtime'
}
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

$logPath = Join-Path $RuntimeDir 'mt5-supervisor.log'
$statusPath = Join-Path $RuntimeDir 'mt5-supervisor-status.json'
$stopPath = Join-Path $RuntimeDir 'mt5.supervisor.stop'
$restartHistoryPath = Join-Path $RuntimeDir 'mt5-supervisor-restart-history.json'
$restartTimes = New-Object System.Collections.Generic.List[datetime]

function Load-RestartHistory {
    if (-not (Test-Path -LiteralPath $restartHistoryPath -PathType Leaf)) { return }
    try {
        $raw = Get-Content -LiteralPath $restartHistoryPath -Raw -ErrorAction Stop
        # A corrupt restart history must not silently reset the restart budget.
        if ([string]::IsNullOrWhiteSpace($raw) -or $raw.Trim() -notmatch '(?s)^\[.*\]$') {
            throw 'Formato do histórico de reinícios inválido: era esperada uma lista JSON.'
        }
        $items = ConvertFrom-Json -InputObject $raw -ErrorAction Stop
        $previousRestart = [datetime]::MinValue
        $futureLimit = (Get-Date).ToUniversalTime().AddMinutes(5)
        foreach ($item in @($items)) {
            if ($item -isnot [string]) {
                throw 'Formato do histórico de reinícios inválido: cada registro deve ser uma data textual.'
            }
            $parsedRestart = [datetime]::Parse($item).ToUniversalTime()
            if ($parsedRestart -gt $futureLimit) {
                throw 'Formato do histórico de reinícios inválido: existe data no futuro.'
            }
            if ($parsedRestart -lt $previousRestart) {
                throw 'Formato do histórico de reinícios inválido: registros fora de ordem cronológica.'
            }
            $restartTimes.Add($parsedRestart.ToLocalTime())
            $previousRestart = $parsedRestart
        }
    } catch {
        $restartTimes.Clear()
        $message = "Histórico de reinícios inválido; supervisor MT5 interrompido para preservar o limite de segurança: $($_.Exception.Message)"
        Write-SupervisorLog $message
        Write-SupervisorStatus 'FAILED' 'RESTART_HISTORY_INVALID'
        throw $message
    }
}

function Save-RestartHistory {
    $values = @($restartTimes | ForEach-Object { $_.ToUniversalTime().ToString('o') })
    $tmp = Join-Path $RuntimeDir (".$([System.IO.Path]::GetFileName($restartHistoryPath)).$([guid]::NewGuid().ToString('N')).tmp")
    try {
        $json = ConvertTo-Json -InputObject @($values) -Depth 3
        Set-Content -LiteralPath $tmp -Value $json -Encoding UTF8
        Move-Item -LiteralPath $tmp -Destination $restartHistoryPath -Force
    } finally {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    }
}

$finalState = 'STOPPED'
$finalReason = 'Supervisor finalizado.'

function Write-SupervisorLog([string]$Message) {
    Add-Content -LiteralPath $logPath -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
}

function Write-SupervisorStatus([string]$State, [string]$Reason) {
    $payload = @{
        component = 'mt5'
        state = $State
        reason = $Reason
        observed_at = (Get-Date).ToUniversalTime().ToString('o')
        process_name = [System.IO.Path]::GetFileNameWithoutExtension($Mt5TerminalPath)
        restart_count_last_hour = $restartTimes.Count
    } | ConvertTo-Json -Compress
    $tmp = "$statusPath.tmp"
    Set-Content -LiteralPath $tmp -Value $payload -Encoding UTF8
    Move-Item -LiteralPath $tmp -Destination $statusPath -Force
}

Load-RestartHistory

$script:LastMt5HealthDiagnostic = 'health_check_not_run'

function Test-Mt5TerminalHealth {
    $script:LastMt5HealthDiagnostic = ''
    try {
        $env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
            $ProjectRoot
        } else {
            "$ProjectRoot;$($env:PYTHONPATH)"
        }
        Set-Location $ProjectRoot
        $healthCheckCode = @'
import json, MetaTrader5 as mt5, os, sys
path = sys.argv[1]
ok = mt5.initialize(path=path)
terminal = mt5.terminal_info() if ok else None
account = mt5.account_info() if ok else None
demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", None)
expected = os.path.normcase(os.path.realpath(path))
actual = os.path.normcase(os.path.realpath(os.path.join(getattr(terminal, "path", ""), os.path.basename(path)))) if terminal else ""
connected = bool(terminal is not None and getattr(terminal, "connected", False))
path_mismatch = bool(terminal is not None and actual != expected)
demo_confirmed = bool(account is not None and demo_mode is not None and getattr(account, "trade_mode", None) == demo_mode)
healthy = bool(ok and terminal is not None and connected and not path_mismatch and demo_confirmed)
diagnostic = {
    "initialize": bool(ok),
    "last_error": repr(mt5.last_error()),
    "terminal_connected": connected,
    "configured_terminal_path_mismatch": path_mismatch,
    "account_not_confirmed_demo": not demo_confirmed,
    "expected_terminal_path": expected,
    "actual_terminal_path": actual,
    "account_info_present": account is not None,
    "healthy": healthy,
}
print("MT5_HEALTH_DIAGNOSTIC=" + json.dumps(diagnostic, sort_keys=True))
mt5.shutdown()
raise SystemExit(0 if healthy else 1)
'@
        $encodedHealthCode = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($healthCheckCode))
        $oneLineHealthCode = "import base64;exec(compile(base64.b64decode('$encodedHealthCode'),'<mt5-health>','exec'))"
        $healthOutput = @(& $PythonExe -c $oneLineHealthCode $Mt5TerminalPath 2>&1)
        $healthExitCode = $LASTEXITCODE
        foreach ($line in $healthOutput) {
            $text = [string]$line
            if ($text -like 'MT5_HEALTH_DIAGNOSTIC=*') {
                $script:LastMt5HealthDiagnostic = $text
                Write-SupervisorLog $text
            } elseif (-not [string]::IsNullOrWhiteSpace($text)) {
                Write-SupervisorLog "Diagnóstico do health gate MT5: $text"
            }
        }
        if ($healthExitCode -ne 0 -and [string]::IsNullOrWhiteSpace($script:LastMt5HealthDiagnostic)) {
            $script:LastMt5HealthDiagnostic = 'MT5_HEALTH_DIAGNOSTIC=' + (@{ healthy = $false; reason = 'python_health_check_failed'; exit_code = $healthExitCode } | ConvertTo-Json -Compress)
            Write-SupervisorLog $script:LastMt5HealthDiagnostic
        }
        return ($healthExitCode -eq 0)
    } catch {
        $script:LastMt5HealthDiagnostic = 'MT5_HEALTH_DIAGNOSTIC=' + (@{ healthy = $false; reason = 'powershell_exception'; detail = ($_.Exception.Message -replace '[\r\n]', ' ') } | ConvertTo-Json -Compress)
        Write-SupervisorLog "Diagnóstico do health gate MT5: $script:LastMt5HealthDiagnostic"
        return $false
    }
}

function Get-ConfiguredMt5Process {
    # Fail closed if multiple matching instances make ownership ambiguous.
    $configuredPath = [System.IO.Path]::GetFullPath($Mt5TerminalPath)
    $candidates = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -ieq ([System.IO.Path]::GetFileName($configuredPath)) -and
            -not [string]::IsNullOrWhiteSpace($_.ExecutablePath) -and
            [string]::Equals(
                [System.IO.Path]::GetFullPath($_.ExecutablePath),
                $configuredPath,
                [System.StringComparison]::OrdinalIgnoreCase
            )
        })
    if ($candidates.Count -gt 1) {
        $reason = 'Mais de uma instância corresponde ao terminal MT5 configurado; estado ambíguo, nenhuma instância será encerrada.'
        Write-SupervisorStatus 'FAILED' $reason
        throw $reason
    }
    if ($candidates.Count -eq 0) { return $null }
    return Get-Process -Id $candidates[0].ProcessId -ErrorAction SilentlyContinue
}

function Get-Mt5AccountSafetyState {
    # A terminal may be stopped automatically only when its configured account is explicitly confirmed DEMO.
    try {
        $accountCheckCode = @'
import MetaTrader5 as mt5, os, sys
path = sys.argv[1]
state = "UNKNOWN"
try:
    ok = mt5.initialize(path=path)
    terminal = mt5.terminal_info() if ok else None
    account = mt5.account_info() if ok else None
    demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", None)
    expected = os.path.normcase(os.path.realpath(path))
    actual = os.path.normcase(os.path.realpath(os.path.join(getattr(terminal, "path", ""), os.path.basename(path)))) if terminal else ""
    if ok and terminal is not None and actual == expected and account is not None and demo_mode is not None:
        state = "DEMO" if getattr(account, "trade_mode", None) == demo_mode else "NON_DEMO"
finally:
    mt5.shutdown()
print(state)
'@
        $encodedAccountCode = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($accountCheckCode))
        $oneLineAccountCode = "import base64;exec(compile(base64.b64decode('$encodedAccountCode'),'<mt5-account-safety>','exec'))"
        $result = & $PythonExe -c $oneLineAccountCode $Mt5TerminalPath 2>$null
        if ($LASTEXITCODE -ne 0) { return 'UNKNOWN' }
        $state = [string]($result | Select-Object -Last 1)
        if ($state.Trim() -in @('DEMO', 'NON_DEMO', 'UNKNOWN')) { return $state.Trim() }
        return 'UNKNOWN'
    } catch {
        return 'UNKNOWN'
    }
}

function Stop-Mt5Process {
    param([System.Diagnostics.Process]$Process)
    if ($null -eq $Process -or $Process.HasExited) { return }
    $accountSafetyState = Get-Mt5AccountSafetyState
    if ($accountSafetyState -ne 'DEMO') {
        $reason = "MT5 não será encerrado automaticamente: conta/caminho não confirmados como DEMO (estado=$accountSafetyState)."
        Write-SupervisorLog $reason
        Write-SupervisorStatus 'FAILED' $reason
        throw $reason
    }
    Write-SupervisorLog "MT5 DEMO não passou no health gate; encerrando PID $($Process.Id) para recuperação limpa."
    & taskkill.exe /PID $Process.Id /T /F 2>$null | Out-Null
    Start-Sleep -Seconds 3
}

function Wait-Mt5Health {
    param([int]$WaitSeconds)
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path -LiteralPath $stopPath -PathType Leaf) { return $false }
        if (Test-Mt5TerminalHealth) { return $true }
        Start-Sleep -Seconds $HealthPollSeconds
    }
    return $false
}

if (-not (Test-Path -LiteralPath $Mt5TerminalPath -PathType Leaf)) {
    $finalState = 'FAILED'
    $finalReason = 'MT5 terminal não encontrado.'
    Write-SupervisorStatus $finalState $finalReason
    throw "MT5 terminal não encontrado: $Mt5TerminalPath"
}

Write-SupervisorLog 'Supervisor MT5 iniciado.'
while (-not (Test-Path -LiteralPath $stopPath -PathType Leaf)) {
    $processName = [System.IO.Path]::GetFileNameWithoutExtension($Mt5TerminalPath)
    $process = Get-ConfiguredMt5Process

    if ($null -ne $process) {
        Write-SupervisorStatus 'STARTING' 'Processo MT5 encontrado; validando conexão do terminal e conta DEMO.'
        if (Wait-Mt5Health -WaitSeconds $HealthWaitSeconds) {
            Write-SupervisorStatus 'HEALTHY' 'MT5 em execução, terminal conectado e conta DEMO confirmada.'
            $healthFailures = 0
            while (-not $process.HasExited) {
                if (Test-Path -LiteralPath $stopPath -PathType Leaf) {
                    Write-SupervisorLog 'Parada controlada detectada enquanto o MT5 estava saudável.'
                    Stop-Mt5Process -Process $process
                    break
                }
                if (Test-Mt5TerminalHealth) {
                    $healthFailures = 0
                } else {
                    $healthFailures++
                    Write-SupervisorLog "Health do MT5 falhou ($healthFailures/$HealthFailureThreshold) enquanto o processo permanecia ativo."
                    if ($healthFailures -ge $HealthFailureThreshold) {
                        Write-SupervisorLog 'Health do MT5 permaneceu indisponível; iniciando recuperação supervisionada.'
                        Stop-Mt5Process -Process $process
                        break
                    }
                }
                Start-Sleep -Seconds $HealthPollSeconds
            }
            if (Test-Path -LiteralPath $stopPath -PathType Leaf) { break }
        } else {
            if (Test-Path -LiteralPath $stopPath -PathType Leaf) { break }
            Stop-Mt5Process -Process $process
        }
    }

    $now = Get-Date
    while ($restartTimes.Count -gt 0 -and $restartTimes[0] -lt $now.AddHours(-1)) {
        $restartTimes.RemoveAt(0)
    }

    if ($restartTimes.Count -ge $MaxRestartsPerHour) {
        Write-SupervisorLog "Limite de reinícios atingido ($MaxRestartsPerHour/h). MT5 entra em espera controlada; o supervisor continuará ativo."
        $finalState = 'RECOVERING'
        $finalReason = 'RESTART_LIMIT_EXCEEDED; aguardando cooldown para nova tentativa'
        Write-SupervisorStatus $finalState $finalReason

        # Keep supervision alive without retrying in a tight loop. Resume when
        # the oldest restart falls outside the one-hour rolling window.
        $retryAt = $restartTimes[0].AddHours(1)
        while ((Get-Date) -lt $retryAt) {
            if (Test-Path -LiteralPath $stopPath -PathType Leaf) { break }
            $remainingSeconds = [int][Math]::Ceiling(($retryAt - (Get-Date)).TotalSeconds)
            if ($remainingSeconds -le 0) { break }
            Start-Sleep -Seconds ([Math]::Min(60, $remainingSeconds))
        }
        if (Test-Path -LiteralPath $stopPath -PathType Leaf) {
            $finalState = 'STOPPED'
            $finalReason = 'Parada controlada durante espera de recuperação.'
            break
        }
        continue
    }

    Write-SupervisorLog 'MT5 não está saudável; iniciando/reiniciando.'
    Start-Process -FilePath $Mt5TerminalPath -WorkingDirectory (Split-Path -Parent $Mt5TerminalPath) | Out-Null
    $restartTimes.Add($now)
    Save-RestartHistory
    Write-SupervisorStatus 'STARTING' 'MT5 iniciado pelo supervisor; aguardando health gate DEMO.'

    if (Wait-Mt5Health -WaitSeconds $HealthWaitSeconds) {
        Write-SupervisorLog 'MT5 saudável: terminal conectado e conta DEMO confirmada.'
        Write-SupervisorStatus 'HEALTHY' 'MT5 em execução, terminal conectado e conta DEMO confirmada.'
        $healthFailures = 0
        $processAfterStart = Get-ConfiguredMt5Process
        while ($null -ne $processAfterStart -and -not $processAfterStart.HasExited) {
            if (Test-Path -LiteralPath $stopPath -PathType Leaf) {
                Write-SupervisorLog 'Parada controlada detectada enquanto o MT5 estava saudável.'
                Stop-Mt5Process -Process $processAfterStart
                break
            }
            if (Test-Mt5TerminalHealth) {
                $healthFailures = 0
            } else {
                $healthFailures++
                Write-SupervisorLog "Health do MT5 falhou ($healthFailures/$HealthFailureThreshold) enquanto o processo permanecia ativo."
                if ($healthFailures -ge $HealthFailureThreshold) {
                    Write-SupervisorLog 'Health do MT5 permaneceu indisponível; iniciando recuperação supervisionada.'
                    Stop-Mt5Process -Process $processAfterStart
                    break
                }
            }
            Start-Sleep -Seconds $HealthPollSeconds
            $processAfterStart = Get-ConfiguredMt5Process
        }
        if (Test-Path -LiteralPath $stopPath -PathType Leaf) { break }
        if ($null -ne $processAfterStart -and -not $processAfterStart.HasExited) { continue }
    }

    $processAfterStart = Get-ConfiguredMt5Process
    if ($null -ne $processAfterStart) {
        Stop-Mt5Process -Process $processAfterStart
    }
    Write-SupervisorLog "MT5 não alcançou o health gate em $HealthWaitSeconds s; nova tentativa após backoff."
    Write-SupervisorStatus 'RECOVERING' 'MT5 sem health DEMO; nova tentativa após backoff.'
    Start-Sleep -Seconds $RestartDelaySeconds
}

if (Test-Path -LiteralPath $stopPath -PathType Leaf) {
    Write-SupervisorLog 'Parada controlada solicitada pelo marcador do runtime.'
    Remove-Item -LiteralPath $stopPath -Force -ErrorAction SilentlyContinue
}
Write-SupervisorStatus $finalState $finalReason
