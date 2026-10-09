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
        $items = Get-Content -LiteralPath $restartHistoryPath -Raw | ConvertFrom-Json
        foreach ($item in @($items)) {
            $restartTimes.Add([datetime]::Parse($item).ToLocalTime())
        }
    } catch {
        $restartTimes.Clear()
        $message = "Histórico de reinícios inválido; supervisor interrompido para preservar o limite de segurança: $($_.Exception.Message)"
        Write-SupervisorLog $message
        throw $message
    }
}

function Save-RestartHistory {
    $values = @($restartTimes | ForEach-Object { $_.ToUniversalTime().ToString('o') })
    $tmp = "$restartHistoryPath.tmp"
    $values | ConvertTo-Json | Set-Content -LiteralPath $tmp -Encoding UTF8
    Move-Item -LiteralPath $tmp -Destination $restartHistoryPath -Force
}

Load-RestartHistory
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

function Test-Mt5TerminalHealth {
    try {
        $env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
            $ProjectRoot
        } else {
            "$ProjectRoot;$($env:PYTHONPATH)"
        }
        Set-Location $ProjectRoot
        $healthCheckCode = @'
import os
import sys
import MetaTrader5 as mt5

configured_terminal = os.path.normcase(os.path.realpath(sys.argv[1]))
configured_directory = os.path.normcase(os.path.dirname(configured_terminal))
ok = mt5.initialize(path=sys.argv[1])
terminal = mt5.terminal_info() if ok else None
account = mt5.account_info() if ok else None
demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", None)
actual_directory = os.path.normcase(os.path.realpath(getattr(terminal, "path", ""))) if terminal is not None else ""
healthy = (
    ok
    and terminal is not None
    and bool(getattr(terminal, "connected", False))
    and actual_directory == configured_directory
    and account is not None
    and demo_mode is not None
    and getattr(account, "trade_mode", None) == demo_mode
)
mt5.shutdown()
raise SystemExit(0 if healthy else 1)
'@
        & $PythonExe -c $healthCheckCode $Mt5TerminalPath
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Get-ConfiguredMt5Process {
    try {
        $configuredPath = [System.IO.Path]::GetFullPath($Mt5TerminalPath)
        $candidate = Get-CimInstance Win32_Process -ErrorAction Stop |
            Where-Object {
                -not [string]::IsNullOrWhiteSpace($_.ExecutablePath) -and
                [string]::Equals(
                    [System.IO.Path]::GetFullPath($_.ExecutablePath),
                    $configuredPath,
                    [System.StringComparison]::OrdinalIgnoreCase
                )
            } |
            Select-Object -First 1
        if ($null -eq $candidate) { return $null }
        return Get-Process -Id $candidate.ProcessId -ErrorAction Stop
    } catch {
        $message = "Não foi possível identificar com segurança o processo do terminal configurado: $($_.Exception.Message)"
        Write-SupervisorLog $message
        # Fail closed: an unknown process state must not be treated as "MT5 absent",
        # otherwise the supervisor could launch a duplicate terminal.
        throw $message
    }
}

function Stop-Mt5Process {
    param([System.Diagnostics.Process]$Process)
    if ($null -eq $Process -or $Process.HasExited) { return }
    Write-SupervisorLog "MT5 não passou no health gate; encerrando PID $($Process.Id) para recuperação limpa."
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
        Write-SupervisorLog "Limite de reinícios atingido ($MaxRestartsPerHour/h). MT5 permanece parado."
        $finalState = 'FAILED'
        $finalReason = 'RESTART_LIMIT_EXCEEDED'
        Write-SupervisorStatus $finalState $finalReason
        break
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
