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
if ([string]::IsNullOrWhiteSpace($RuntimeDir)) { $RuntimeDir = Join-Path $ProjectRoot '.runtime' }
$RuntimeDir = [System.IO.Path]::GetFullPath($RuntimeDir)

# Pin the child app to the validated local DEMO runtime. Do not inherit stale
# machine-level values that could point state elsewhere, expose a public bind,
# or enable REAL through an old environment setting.
$env:CONTROLADOR_BIND_HOST = '127.0.0.1'
$env:PORT = '8000'
$env:CONTROLADOR_EXECUTION_PROVIDER = 'ic_markets_mt5_demo'
$env:CONTROLADOR_RUNTIME_DIR = $RuntimeDir
$env:CONTROLADOR_SECURITY_AUDIT_DB = Join-Path $RuntimeDir 'security-audit.sqlite'
$env:CONTROLADOR_REMOTE_ACCESS_REQUIRED = 'true'
$env:CONTROLADOR_LOCAL_MUTATIONS_ALLOWED = 'true'
$env:CONTROLADOR_LOCAL_MUTATION_HOSTS = 'localhost,127.0.0.1,[::1]'
$env:CONTROLADOR_TRUSTED_IDENTITY_HEADER = 'Cf-Access-Authenticated-User-Email'
$env:CONTROLADOR_REAL_EXPLICITLY_ENABLED = 'false'
$env:CONTROLADOR_REAL_EXECUTION_ALLOWED = 'false'
$env:CONTROLADOR_REAL_AUDIT_VERIFIED = 'false'
$env:CONTROLADOR_REAL_RISK_APPROVED = 'false'
$env:CONTROLADOR_REAL_AUTHORIZATION_ID = ''
$env:CONTROLADOR_REAL_AUDIT_ID = ''
$env:CONTROLADOR_REAL_ADMISSION_ID = ''

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
        $raw = Get-Content -LiteralPath $restartHistoryPath -Raw -ErrorAction Stop
        # ConvertFrom-Json can accept scalar JSON such as null or a string.
        # Only the persisted JSON array contract is valid; malformed history
        # must stop the supervisor rather than silently reset its restart budget.
        if ([string]::IsNullOrWhiteSpace($raw) -or $raw.Trim() -notmatch '(?s)^\[.*\]$') {
            throw 'Formato do histórico de reinícios inválido: era esperada uma lista JSON.'
        }
        $items = ConvertFrom-Json -InputObject $raw -ErrorAction Stop
        foreach ($item in @($items)) {
            if ($item -isnot [string]) {
                throw 'Formato do histórico de reinícios inválido: cada registro deve ser uma data textual.'
            }
            $restartTimes.Add([datetime]::Parse($item).ToLocalTime())
        }
    } catch {
        $restartTimes.Clear()
        $message = "Histórico de reinícios inválido; supervisor interrompido para preservar o limite de segurança: $($_.Exception.Message)"
        Write-StartupLog $message
        Write-SupervisorStatus 'FAILED' 'RESTART_HISTORY_INVALID'
        throw $message
    }
}

function Save-RestartHistory {
    $values = @($restartTimes | ForEach-Object { $_.ToUniversalTime().ToString('o') })
    $tmp = Join-Path $RuntimeDir (".$([System.IO.Path]::GetFileName($restartHistoryPath)).$([guid]::NewGuid().ToString('N')).tmp")
    try {
        $values | ConvertTo-Json | Set-Content -LiteralPath $tmp -Encoding UTF8
        Move-Item -LiteralPath $tmp -Destination $restartHistoryPath -Force
    } finally {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    }
}

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

Load-RestartHistory

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

        # Contrato canonico atual do /api/health.
        if ($payload.ok -ne $true) { return $false }
        if ($payload.execution_allowed -ne $false) { return $false }
        if ($payload.real -ne "DESABILITADO") { return $false }

        # Estado operacional detalhado.
        $op = $payload.operational_observability.execution
        if ($null -eq $op) { return $false }
        if ($op.allowed -ne $false) { return $false }
        if ($op.real -ne "DISABLED") { return $false }

        # Camada independente de REAL.
        $realRuntime = $payload.real_runtime
        if ($null -eq $realRuntime) { return $false }
        if ($realRuntime.real_execution_allowed -ne $false) { return $false }
        if ($realRuntime.explicitly_enabled -ne $false) { return $false }

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

function Stop-ControllerProcess {
    param(
        [System.Diagnostics.Process]$Process,
        [string]$Reason = "Health não respondeu dentro de $HealthWaitSeconds s"
    )
    if ($null -eq $Process -or $Process.HasExited) { return }
    Write-StartupLog "$Reason; encerrando PID $($Process.Id) para recuperação limpa."
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
    try {
        $existingControllers = @(
            Get-CimInstance Win32_Process -ErrorAction Stop |
                Where-Object {
                    $_.Name -match '^(python|python3)(\\.exe)?$' -and
                    $_.CommandLine -like "*$ProjectRoot*app.py*"
                }
        )
    } catch {
        $message = "Não foi possível identificar com segurança processos existentes do Controlador: $($_.Exception.Message)"
        Write-StartupLog $message
        Write-SupervisorStatus 'FAILED' 'PROCESS_DISCOVERY_FAILED'
        throw $message
    }
    if ($existingControllers.Count -gt 1) {
        $message = "Mais de uma instância potencial do Controlador foi encontrada; estado ambíguo, sem iniciar ou encerrar processos automaticamente."
        Write-StartupLog $message
        Write-SupervisorStatus 'FAILED' 'DUPLICATE_CONTROLLER_PROCESSES'
        throw $message
    }
    $existingController = if ($existingControllers.Count -eq 1) { $existingControllers[0] } else { $null }
    $process = $null
    if ($null -ne $existingController) {
        Write-StartupLog "Instância existente detectada (PID $($existingController.ProcessId)); verificando /api/health antes de declarar HEALTHY."
        if (Test-ControllerHealth) {
            $process = Get-Process -Id $existingController.ProcessId -ErrorAction Stop
            Write-SupervisorStatus 'HEALTHY' 'Instância existente detectada e /api/health respondeu 2xx; entrando no monitoramento contínuo.'
        } else {
            Write-StartupLog 'Instância existente não respondeu /api/health; encerrando-a para evitar estado falso/duplicado.'
            & taskkill.exe /PID $existingController.ProcessId /T /F 2>$null | Out-Null
            Start-Sleep -Seconds 2
        }
    }

    if ($null -eq $process) {
        Write-StartupLog 'Iniciando app.py sob supervisão.'
        if (Test-Path -LiteralPath $appStdoutPath) { Remove-Item -LiteralPath $appStdoutPath -Force -ErrorAction SilentlyContinue }
        if (Test-Path -LiteralPath $appStderrPath) { Remove-Item -LiteralPath $appStderrPath -Force -ErrorAction SilentlyContinue }

        $appPath = Join-Path $ProjectRoot 'app.py'
        $process = Start-Process -FilePath $PythonExe -ArgumentList @('-u', $appPath) -WorkingDirectory $ProjectRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput $appStdoutPath -RedirectStandardError $appStderrPath
        Write-SupervisorStatus 'STARTING' "app.py iniciado; aguardando /api/health (PID $($process.Id))."
    }

    $healthy = Wait-ControllerHealth -Process $process -WaitSeconds $HealthWaitSeconds
    if ($healthy) {
        Write-StartupLog "Controlador saudável: /api/health respondeu 2xx (PID $($process.Id))."
        Write-SupervisorStatus 'HEALTHY' 'app.py ativo e /api/health respondeu 2xx.'
        $healthFailures = 0
        while (-not $process.HasExited) {
            if (Test-Path -LiteralPath $stopPath -PathType Leaf) {
                Write-StartupLog 'Parada controlada detectada enquanto o Controlador estava saudável.'
                Stop-ControllerProcess -Process $process -Reason 'Parada controlada solicitada pelo runtime'
                break
            }
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
        $appExitCode = if ($process.HasExited) { $process.ExitCode } else { -1 }
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
