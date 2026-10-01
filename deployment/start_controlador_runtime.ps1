param(
    [string]$ProjectRoot = 'C:\Controlador-trade',
    [string]$PythonExe = 'python',
    [string]$RuntimeDir = '',
    [int]$Mt5WaitSeconds = 180,
    [int]$RestartDelaySeconds = 10,
    [int]$MaxRestartsPerHour = 6
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RuntimeDir)) { $RuntimeDir = Join-Path $ProjectRoot '.runtime' }

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
$logPath = Join-Path $RuntimeDir 'controlador-startup.log'
$statusPath = Join-Path $RuntimeDir 'controlador-supervisor-status.json'
$stopPath = Join-Path $RuntimeDir 'controlador.supervisor.stop'
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

function Write-StartupLog([string]$Message) {
    Add-Content -LiteralPath $logPath -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
}

function Write-SupervisorStatus([string]$State, [string]$Reason) {
    $payload = @{
        component = 'controlador'
        state = $State
        reason = $Reason
        observed_at = (Get-Date).ToUniversalTime().ToString('o')
        restart_count_last_hour = $restartTimes.Count
    } | ConvertTo-Json -Compress
    $tmp = "$statusPath.tmp"
    Set-Content -LiteralPath $tmp -Value $payload -Encoding UTF8
    Move-Item -LiteralPath $tmp -Destination $statusPath -Force
}

function Test-Mt5Demo {
    param([int]$WaitSeconds)
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            & $PythonExe -c "import MetaTrader5 as mt5; from execution.mt5_demo_runtime_preflight import run_preflight; r=run_preflight(mt5); raise SystemExit(0 if r.available and r.demo else 1)"
            if ($LASTEXITCODE -eq 0) { return $true }
        } catch {}
        Start-Sleep -Seconds 5
    }
    return $false
}

Set-Location $ProjectRoot
Write-StartupLog 'Supervisor do Controlador iniciado.'

while (-not (Test-Path -LiteralPath $stopPath -PathType Leaf)) {
    Write-SupervisorStatus 'STARTING' 'Pré-verificação DEMO antes de iniciar o Controlador.'
    $demoReady = Test-Mt5Demo -WaitSeconds $Mt5WaitSeconds

    if ($demoReady) {
        Write-StartupLog 'MT5 DEMO confirmado; iniciando Controlador.'
    } else {
        Write-StartupLog 'MT5 DEMO não confirmado; Controlador será iniciado, mas execução deve permanecer bloqueada pelo safety gate.'
    }

    # A task restart can overlap an older app process that survived. Do not
    # create a second controller instance; app.py also owns the runtime lock.
    $existingController = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^(python|python3)(\.exe)?$' -and
            $_.CommandLine -like "*$ProjectRoot*app.py*"
        } |
        Select-Object -First 1

    if ($null -ne $existingController) {
        Write-StartupLog 'Controlador já está em execução; supervisor não criará segunda instância.'
        Write-SupervisorStatus 'HEALTHY' 'Instância existente detectada.'
        Start-Sleep -Seconds 10
        continue
    }

    Write-StartupLog 'Iniciando app.py sob supervisão.'
    Write-SupervisorStatus 'HEALTHY' 'Controlador iniciado pelo supervisor.'
    & $PythonExe -u (Join-Path $ProjectRoot 'app.py') >> $logPath 2>&1
    $appExitCode = $LASTEXITCODE
    Write-StartupLog "Controlador finalizado com código de saída $appExitCode."

    if (Test-Path -LiteralPath $stopPath -PathType Leaf) { break }

    $now = Get-Date
    while ($restartTimes.Count -gt 0 -and $restartTimes[0] -lt $now.AddHours(-1)) {
        $restartTimes.RemoveAt(0)
    }

    if ($restartTimes.Count -ge $MaxRestartsPerHour) {
        Write-StartupLog "Limite de reinícios atingido ($MaxRestartsPerHour/h). Controlador permanece parado."
        Write-SupervisorStatus 'FAILED' 'RESTART_LIMIT_EXCEEDED'
        break
    }

    $restartTimes.Add($now)
    Save-RestartHistory
    Write-SupervisorStatus 'RECOVERING' "Controlador terminou com código $appExitCode; nova tentativa após backoff."
    Start-Sleep -Seconds $RestartDelaySeconds
}

if (Test-Path -LiteralPath $stopPath -PathType Leaf) {
    Write-StartupLog 'Parada controlada solicitada pelo marcador do runtime.'
    Remove-Item -LiteralPath $stopPath -Force -ErrorAction SilentlyContinue
}
Write-SupervisorStatus 'STOPPED' 'Supervisor finalizado.'
