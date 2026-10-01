param(
    [Parameter(Mandatory = $true)]
    [string]$Mt5TerminalPath,
    [string]$RuntimeDir = '',
    [int]$RestartDelaySeconds = 10,
    [int]$MaxRestartsPerHour = 6
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RuntimeDir)) {
    $RuntimeDir = Join-Path (Split-Path -Parent (Split-Path -Parent $Mt5TerminalPath)) '.runtime'
}
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

$logPath = Join-Path $RuntimeDir 'mt5-supervisor.log'
$statusPath = Join-Path $RuntimeDir 'mt5-supervisor-status.json'
$stopPath = Join-Path $RuntimeDir 'mt5.supervisor.stop'
$restartHistoryPath = Join-Path $RuntimeDir 'supervisor-restart-history.json'
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
if (-not (Test-Path -LiteralPath $Mt5TerminalPath -PathType Leaf)) {
    Write-SupervisorStatus 'FAILED' 'MT5 terminal não encontrado.'
    throw "MT5 terminal não encontrado: $Mt5TerminalPath"
}

Write-SupervisorLog 'Supervisor MT5 iniciado.'
while (-not (Test-Path -LiteralPath $stopPath -PathType Leaf)) {
    $process = Get-Process -Name $processName -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $process) {
        $now = Get-Date
        while ($restartTimes.Count -gt 0 -and $restartTimes[0] -lt $now.AddHours(-1)) {
            $restartTimes.RemoveAt(0)
        }
        if ($restartTimes.Count -ge $MaxRestartsPerHour) {
            Write-SupervisorLog "Limite de reinícios atingido ($MaxRestartsPerHour/h). MT5 permanece parado."
            Write-SupervisorStatus 'FAILED' 'RESTART_LIMIT_EXCEEDED'
            break
        }

        Write-SupervisorLog 'MT5 não está em execução; iniciando/reiniciando.'
        Start-Process -FilePath $Mt5TerminalPath
        $restartTimes.Add($now)
        Write-SupervisorStatus 'STARTING' 'MT5 iniciado pelo supervisor.'
        Start-Sleep -Seconds $RestartDelaySeconds
    }
    else {
        Write-SupervisorStatus 'HEALTHY' 'Processo MT5 observado em execução.'
        Start-Sleep -Seconds 10
    }
}

if (Test-Path -LiteralPath $stopPath -PathType Leaf) {
    Write-SupervisorLog 'Parada controlada solicitada pelo marcador do runtime.'
    Remove-Item -LiteralPath $stopPath -Force -ErrorAction SilentlyContinue
}
Write-SupervisorStatus 'STOPPED' 'Supervisor finalizado.'