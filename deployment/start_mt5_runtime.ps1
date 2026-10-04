param(
    [Parameter(Mandatory = $true)]
    [string]$Mt5TerminalPath,
    [string]$ProjectRoot = 'C:\Controlador-trade',
    [string]$PythonExe = 'python',
    [string]$RuntimeDir = '',
    [int]$RestartDelaySeconds = 10,
    [int]$MaxRestartsPerHour = 6,
    [int]$Mt5WaitSeconds = 180
)

$ErrorActionPreference = 'Stop'
Set-Location $ProjectRoot
if ([string]::IsNullOrWhiteSpace($RuntimeDir)) {
    $RuntimeDir = Join-Path (Split-Path -Parent (Split-Path -Parent $Mt5TerminalPath)) '.runtime'
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

$processName = [System.IO.Path]::GetFileNameWithoutExtension($Mt5TerminalPath)

function Test-Mt5Demo {
    param([int]$WaitSeconds)

    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ((Get-Date) -lt $deadline -and -not (Test-Path -LiteralPath $stopPath -PathType Leaf)) {
        try {
            & $PythonExe -c "import MetaTrader5 as mt5; from execution.mt5_demo_runtime_preflight import run_preflight; r=run_preflight(mt5); raise SystemExit(0 if r.available and r.demo else 1)"
            if ($LASTEXITCODE -eq 0) {
                return $true
            }
        } catch {
            Write-SupervisorLog "Falha ao executar pré-verificação DEMO: $($_.Exception.Message)"
        }
        Start-Sleep -Seconds 5
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
    $process = Get-Process -Name $processName -ErrorAction SilentlyContinue | Select-Object -First 1
    $startedBySupervisor = $false

    if ($null -eq $process) {
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

        Write-SupervisorLog 'MT5 não está em execução; iniciando/reiniciando.'
        Start-Process -FilePath $Mt5TerminalPath
        $startedBySupervisor = $true
        $restartTimes.Add($now)
        Save-RestartHistory
        Write-SupervisorStatus 'STARTING' 'MT5 iniciado; aguardando pré-verificação DEMO.'
        Start-Sleep -Seconds 5
    }

    Write-SupervisorStatus 'STARTING' 'MT5 em execução; validando DEMO + símbolo + cotação.'
    if (Test-Mt5Demo -WaitSeconds $Mt5WaitSeconds) {
        Write-SupervisorStatus 'HEALTHY' 'MT5 DEMO + símbolo + cotação validados.'
        Start-Sleep -Seconds 10
        continue
    }

    if ($startedBySupervisor) {
        Write-SupervisorLog 'MT5 iniciado pelo supervisor não confirmou DEMO/readiness; encerrando processo antes de nova tentativa.'
        try {
            $process = Get-Process -Name $processName -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($null -ne $process) {
                Stop-Process -Id $process.Id -Force
            }
        } catch {
            Write-SupervisorLog "Não foi possível encerrar MT5 iniciado pelo supervisor: $($_.Exception.Message)"
        }
    }

    Write-SupervisorStatus 'RECOVERING' 'MT5 está em execução, mas a pré-verificação DEMO/readiness não foi confirmada.'
    Start-Sleep -Seconds $RestartDelaySeconds
}

if (Test-Path -LiteralPath $stopPath -PathType Leaf) {
    Write-SupervisorLog 'Parada controlada solicitada pelo marcador do runtime.'
    Remove-Item -LiteralPath $stopPath -Force -ErrorAction SilentlyContinue
}
Write-SupervisorStatus $finalState $finalReason