param(
    [Parameter(Mandatory = $true)]
    [string]$Mt5TerminalPath,
    [string]$ProjectRoot = 'C:\Controlador-trade',
    [string]$PythonExe = 'python',
    [string]$RuntimeDir = '',
    [int]$RestartDelaySeconds = 10,
    [int]$MaxRestartsPerHour = 6,
    [int]$HealthWaitSeconds = 60,
    [int]$HealthPollSeconds = 5
)

$ErrorActionPreference = 'Stop'
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

function Test-Mt5Demo {
    try {
        $env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
            $ProjectRoot
        } else {
            "$ProjectRoot;$($env:PYTHONPATH)"
        }
        Set-Location $ProjectRoot
        & $PythonExe -c "import MetaTrader5 as mt5; from execution.mt5_demo_runtime_preflight import run_preflight; r=run_preflight(mt5); raise SystemExit(0 if r.available and r.demo else 1)"
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
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
        if (Test-Mt5Demo) { return $true }
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
    $process = Get-Process -Name $processName -ErrorAction SilentlyContinue | Select-Object -First 1

    if ($null -ne $process) {
        Write-SupervisorStatus 'STARTING' 'Processo MT5 encontrado; validando conexão DEMO pelo health gate.'
        if (Wait-Mt5Health -WaitSeconds $HealthWaitSeconds) {
            Write-SupervisorStatus 'HEALTHY' 'MT5 em execução e preflight DEMO confirmado.'
            Start-Sleep -Seconds 10
            continue
        }

        if (Test-Path -LiteralPath $stopPath -PathType Leaf) { break }
        Stop-Mt5Process -Process $process
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
        Write-SupervisorLog 'MT5 saudável: preflight DEMO confirmado.'
        Write-SupervisorStatus 'HEALTHY' 'MT5 em execução e preflight DEMO confirmado.'
        Start-Sleep -Seconds 10
        continue
    }

    $processAfterStart = Get-Process -Name $processName -ErrorAction SilentlyContinue | Select-Object -First 1
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
