param(
    [string]$ProjectRoot = 'C:\Controlador-trade',
    [string]$PythonExe = 'python',
    [string]$RuntimeDir = '',
    [int]$Mt5WaitSeconds = 180,
    [int]$RestartDelaySeconds = 10,
    [int]$MaxRestartsPerHour = 6,
    [int]$HealthWaitSeconds = 60,
    [int]$HealthPollSeconds = 3,
    [int]$HealthFailureThreshold = 3
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RuntimeDir)) { $RuntimeDir = Join-Path $ProjectRoot '.runtime' }

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
$logPath = Join-Path $RuntimeDir 'controlador-startup.log'
$statusPath = Join-Path $RuntimeDir 'controlador-supervisor-status.json'
$stopPath = Join-Path $RuntimeDir 'controlador.supervisor.stop'
$restartHistoryPath = Join-Path $RuntimeDir 'controlador-supervisor-restart-history.json'
$appStdoutPath = Join-Path $RuntimeDir 'controlador-app.stdout.log'
$appStderrPath = Join-Path $RuntimeDir 'controlador-app.stderr.log'
$healthUrl = 'http://127.0.0.1:8000/api/health'
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

function Write-StartupLog([string]$Message) {
    Add-Content -LiteralPath $logPath -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
}

function Write-SupervisorStatus([string]$State, [string]$Reason) {
    $payload = @{
        component = 'controlador'
        state = $State
        reason = $Reason
        health_url = $healthUrl
        observed_at = (Get-Date).ToUniversalTime().ToString('o')
        restart_count_last_hour = $restartTimes.Count
    } | ConvertTo-Json -Compress
    $tmp = "$statusPath.tmp"
    Set-Content -LiteralPath $tmp -Value $payload -Encoding UTF8
    Move-Item -LiteralPath $tmp -Destination $statusPath -Force
}

function Sync-Mt5Panel {
    $syncScript = Join-Path $ProjectRoot 'deployment\sync_mql5_panel.ps1'
    if (-not (Test-Path -LiteralPath $syncScript -PathType Leaf)) {
        Write-StartupLog 'Sincronizador MQL5 não encontrado; seguindo sem alterar o painel.'
        return
    }
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $syncScript -ProjectRoot $ProjectRoot -PythonExe $PythonExe
        if ($LASTEXITCODE -eq 0) {
            Write-StartupLog 'Painel MQL5 sincronizado/compilado automaticamente.'
        } else {
            Write-StartupLog "Sincronização MQL5 terminou com código $LASTEXITCODE; runtime seguirá protegido."
        }
    } catch {
        Write-StartupLog "Falha na sincronização MQL5: $($_.Exception.Message). Runtime seguirá protegido."
    }
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

function Test-ControllerHealth {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 3 -ErrorAction Stop
        if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 300) { return $false }
        $payload = $response.Content | ConvertFrom-Json
        if ($payload.ok -ne $true) { return $false }
        if (-not $payload.PSObject.Properties.Name.Contains("execution")) { return $false }
        if (-not $payload.PSObject.Properties.Name.Contains("real_runtime")) { return $false }
        if ($payload.execution.allowed -eq $true) { return $false }
        if ($payload.execution.real -ne "DISABLED") { return $false }
        return $true
    } catch {
        return $false
    }
}

function Wait-ControllerHealth {
    param(
        [System.Diagnostics.Process]$Process,
        [int]$WaitSeconds
    )
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path -LiteralPath $stopPath -PathType Leaf) { return $false }
        if ($Process.HasExited) {
            Write-StartupLog "app.py terminou durante a inicialização; código $($Process.ExitCode)."
            return $false
        }
        if (Test-ControllerHealth) { return $true }
        Start-Sleep -Seconds $HealthPollSeconds
    }
    return $false
}

function Stop-ControllerProcess([System.Diagnostics.Process]$Process) {
    if ($null -eq $Process -or $Process.HasExited) { return }
    Write-StartupLog "Health não respondeu dentro de $HealthWaitSeconds s; encerrando PID $($Process.Id) para recuperação limpa."
    & taskkill.exe /PID $Process.Id /T /F 2>$null | Out-Null
    Start-Sleep -Seconds 2
}

$env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) { $ProjectRoot } else { "$ProjectRoot;$($env:PYTHONPATH)" }
Set-Location $ProjectRoot
Write-StartupLog 'Supervisor do Controlador iniciado.'

while (-not (Test-Path -LiteralPath $stopPath -PathType Leaf)) {
    Write-SupervisorStatus 'STARTING' 'Pré-verificação DEMO antes de iniciar o Controlador.'
    $demoReady = Test-Mt5Demo -WaitSeconds $Mt5WaitSeconds

    if ($demoReady) {
        Write-StartupLog 'MT5 DEMO confirmado; sincronizando ponte MQL5 antes do Controlador.'
        Sync-Mt5Panel
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
        Write-StartupLog "Instância existente detectada (PID $($existingController.ProcessId)); verificando /api/health antes de declarar HEALTHY."
        if (Test-ControllerHealth) {
            Write-SupervisorStatus 'HEALTHY' 'Instância existente detectada e /api/health respondeu 2xx.'
            Start-Sleep -Seconds 10
            continue
        }
        Write-StartupLog 'Instância existente não respondeu /api/health; encerrando-a para evitar estado falso/duplicado.'
        & taskkill.exe /PID $existingController.ProcessId /T /F 2>$null | Out-Null
        Start-Sleep -Seconds 2
    }

    Write-StartupLog 'Iniciando app.py sob supervisão.'
    if (Test-Path -LiteralPath $appStdoutPath) { Remove-Item -LiteralPath $appStdoutPath -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $appStderrPath) { Remove-Item -LiteralPath $appStderrPath -Force -ErrorAction SilentlyContinue }

    $appPath = Join-Path $ProjectRoot 'app.py'
    $process = Start-Process -FilePath $PythonExe -ArgumentList @('-u', $appPath) -WorkingDirectory $ProjectRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput $appStdoutPath -RedirectStandardError $appStderrPath
    Write-SupervisorStatus 'STARTING' "app.py iniciado; aguardando /api/health (PID $($process.Id))."

    $healthy = Wait-ControllerHealth -Process $process -WaitSeconds $HealthWaitSeconds
    if ($healthy) {
        Write-StartupLog "Controlador saudável: /api/health respondeu 2xx (PID $($process.Id))."
        Write-SupervisorStatus 'HEALTHY' 'app.py ativo e /api/health respondeu 2xx.'
        $healthFailures = 0
        while (-not $process.HasExited) {
            if (Test-ControllerHealth) {
                $healthFailures = 0
            } else {
                $healthFailures++
                Write-StartupLog "Health do Controlador falhou ($healthFailures/$HealthFailureThreshold) enquanto o processo permanecia ativo."
                if ($healthFailures -ge $HealthFailureThreshold) {
                    Write-StartupLog 'Health do Controlador permaneceu indisponível; iniciando recuperação supervisionada.'
                    Stop-ControllerProcess -Process $process
                    break
                }
            }
            Start-Sleep -Seconds $HealthPollSeconds
        }
    } else {
        if (-not $process.HasExited) { Stop-ControllerProcess -Process $process }
        if (Test-Path -LiteralPath $appStdoutPath) { Get-Content -LiteralPath $appStdoutPath -ErrorAction SilentlyContinue | Add-Content -LiteralPath $logPath }
        if (Test-Path -LiteralPath $appStderrPath) { Get-Content -LiteralPath $appStderrPath -ErrorAction SilentlyContinue | Add-Content -LiteralPath $logPath }
        $appExitCode = if ($process.HasExited) { $process.ExitCode } else { -1 }
        Write-StartupLog "Controlador não alcançou /api/health; código observado=$appExitCode."
    }

    if (Test-Path -LiteralPath $stopPath -PathType Leaf) { break }

    $now = Get-Date
    while ($restartTimes.Count -gt 0 -and $restartTimes[0] -lt $now.AddHours(-1)) {
        $restartTimes.RemoveAt(0)
    }

    if ($restartTimes.Count -ge $MaxRestartsPerHour) {
        Write-StartupLog "Limite de reinícios atingido ($MaxRestartsPerHour/h). Controlador permanece parado."
        $finalState = 'FAILED'
        $finalReason = 'RESTART_LIMIT_EXCEEDED'
        Write-SupervisorStatus $finalState $finalReason
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
Write-SupervisorStatus $finalState $finalReason
