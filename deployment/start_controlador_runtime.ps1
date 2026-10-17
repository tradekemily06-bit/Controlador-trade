param(
    [string]$ProjectRoot = 'C:\Controlador-trade',
    [string]$PythonExe = 'python',
    [string]$RuntimeDir = '',
    [string]$Mt5TerminalPath = 'C:\Program Files\MetaTrader 5\terminal64.exe',
    [int]$Mt5WaitSeconds = 180,
    [int]$RestartDelaySeconds = 10,
    [int]$MaxRestartsPerHour = 6,
    [int]$HealthWaitSeconds = 60,
    [int]$HealthPollSeconds = 3,
    [int]$HealthFailureThreshold = 3
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)

if ($PythonExe -eq 'python' -or $PythonExe -eq 'python.exe') {
    $resolvedPython = Get-Command $PythonExe -ErrorAction SilentlyContinue
    if ($null -eq $resolvedPython -or [string]::IsNullOrWhiteSpace($resolvedPython.Source)) {
        throw "Python não foi encontrado no PATH. Informe -PythonExe com o caminho completo do python.exe."
    }
    $PythonExe = $resolvedPython.Source
} elseif (-not [System.IO.Path]::IsPathRooted($PythonExe)) {
    $projectPython = Join-Path $ProjectRoot $PythonExe
    if (Test-Path -LiteralPath $projectPython -PathType Leaf) {
        $PythonExe = [System.IO.Path]::GetFullPath($projectPython)
    }
}
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Python não encontrado: $PythonExe"
}
if ([string]::IsNullOrWhiteSpace($RuntimeDir)) {
    $RuntimeDir = Join-Path $ProjectRoot '.runtime'
} elseif (-not [System.IO.Path]::IsPathRooted($RuntimeDir)) {
    $RuntimeDir = Join-Path $ProjectRoot $RuntimeDir
}
$RuntimeDir = [System.IO.Path]::GetFullPath($RuntimeDir)

# Pin the child app to the validated local DEMO runtime. Do not inherit stale
# machine-level values that could point state elsewhere, expose a public bind,
# or enable REAL through an old environment setting.
$env:CONTROLADOR_BIND_HOST = '127.0.0.1'
$env:PORT = '8000'
$env:CONTROLADOR_EXECUTION_PROVIDER = 'ic_markets_mt5_demo'
$env:CONTROLADOR_MT5_TERMINAL_PATH = $Mt5TerminalPath
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
$maintenanceLockPath = Join-Path $RuntimeDir 'maintenance.lock'
$restartHistoryPath = Join-Path $RuntimeDir 'controlador-supervisor-restart-history.json'
$appStdoutPath = Join-Path $RuntimeDir 'controlador-app.stdout.log'
$appStderrPath = Join-Path $RuntimeDir 'controlador-app.stderr.log'
$healthUrl = 'http://127.0.0.1:8000/api/health'
$restartTimes = New-Object System.Collections.Generic.List[datetime]
$script:RestartHistoryValid = $true
$script:RestartHistoryError = ''

function Load-RestartHistory {
    if (-not (Test-Path -LiteralPath $restartHistoryPath -PathType Leaf)) { return }
    try {
        $rawHistory = Get-Content -LiteralPath $restartHistoryPath -Raw -ErrorAction Stop
        if ([string]::IsNullOrWhiteSpace($rawHistory)) {
            throw 'arquivo de histórico vazio'
        }
        $items = $rawHistory | ConvertFrom-Json -ErrorAction Stop
        foreach ($item in @($items)) {
            $parsedTime = [datetime]::MinValue
            if (-not [datetime]::TryParse([string]$item, [ref]$parsedTime)) {
                throw 'timestamp inválido no histórico de reinícios'
            }
            $restartTimes.Add($parsedTime.ToLocalTime())
        }
        $restartTimes.Sort()
    } catch {
        # Corrupt history must never reset the restart budget and enable retries.
        $script:RestartHistoryValid = $false
        $script:RestartHistoryError = $_.Exception.Message
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
        $syncOutput = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $syncScript -ProjectRoot $ProjectRoot -PythonExe $PythonExe -Mt5TerminalPath $Mt5TerminalPath 2>&1
        $syncExitCode = $LASTEXITCODE
        foreach ($line in @($syncOutput)) {
            $message = [string]$line
            if (-not [string]::IsNullOrWhiteSpace($message)) {
                Write-StartupLog "Sincronização MQL5: $message"
            }
        }
        if ($syncExitCode -eq 0) {
            Write-StartupLog 'Painel MQL5 sincronizado/compilado automaticamente.'
        } else {
            Write-StartupLog "Sincronização MQL5 terminou com código $syncExitCode; runtime seguirá protegido."
        }
    } catch {
        Write-StartupLog "Falha na sincronização MQL5: $($_.Exception.Message). Runtime seguirá protegido."
    }
}

function Test-Mt5Demo {
    param([int]$WaitSeconds)
    if (Test-Path -LiteralPath $maintenanceLockPath -PathType Leaf) {
        Write-StartupLog 'Pré-verificação MT5 ignorada: bloqueio de manutenção ativo; Controlador iniciará com execução bloqueada.'
        return $false
    }
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

function Invoke-RuntimeHttpProbe {
    param(
        [string]$Uri,
        [int]$TimeoutSeconds
    )
    $script:LastRuntimeHttpProbeDiagnostic = ''
    # Use Python urllib with proxy auto-detection disabled. On this Windows
    # runtime, PowerShell's built-in web-request cmdlet can stall far beyond its timeout;
    # the local liveness probe must be cheap and predictably bounded.
    $probeCode = @'
import json, sys, urllib.request
url = sys.argv[1]
timeout = float(sys.argv[2])
request = urllib.request.Request(url, headers={"Connection": "close", "User-Agent": "ControladorSupervisor/1.0"})
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    with opener.open(request, timeout=timeout) as response:
        print(json.dumps({
            "status": int(response.status),
            "body": response.read().decode("utf-8", errors="replace")
        }, separators=(",", ":")))
except Exception as exc:
    print(json.dumps({
        "error": type(exc).__name__,
        "message": str(exc)
    }, separators=(",", ":")))
    raise SystemExit(1)
'@
    $encodedProbeCode = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($probeCode))
    $oneLineProbeCode = "import base64;exec(compile(base64.b64decode('$encodedProbeCode'),'<runtime-http-probe>','exec'))"
    $probeOutput = & $PythonExe -c $oneLineProbeCode $Uri $TimeoutSeconds 2>&1
    $probeExitCode = $LASTEXITCODE
    $lastLine = [string](@($probeOutput | ForEach-Object { [string]$_ } | Select-Object -Last 1))
    if ($probeExitCode -ne 0) {
        $script:LastRuntimeHttpProbeDiagnostic = "probe HTTP local falhou: $lastLine"
        throw $script:LastRuntimeHttpProbeDiagnostic
    }
    $result = $lastLine | ConvertFrom-Json
    if ($null -eq $result.status -or $null -eq $result.body) {
        $script:LastRuntimeHttpProbeDiagnostic = "resposta inválida do probe HTTP local: $lastLine"
        throw $script:LastRuntimeHttpProbeDiagnostic
    }
    $script:LastRuntimeHttpProbeDiagnostic = "HTTP $([int]$result.status)"
    return [pscustomobject]@{
        StatusCode = [int]$result.status
        Content = [string]$result.body
    }
}

function Test-ControllerHealth {
    # Cheap liveness probe. A slow diagnostic/status route must not be treated
    # as a dead process and must not trigger a restart loop.
    $livenessUrl = 'http://127.0.0.1:8000/api/health/live'
    $script:LastControllerLivenessDiagnostic = ''
    try {
        $response = Invoke-RuntimeHttpProbe -Uri $livenessUrl -TimeoutSeconds 3
        if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 300) {
            $script:LastControllerLivenessDiagnostic = "liveness retornou HTTP $($response.StatusCode)"
            return $false
        }
        $payload = $response.Content | ConvertFrom-Json
        if ($payload.ok -ne $true -or $payload.live -ne $true) {
            $script:LastControllerLivenessDiagnostic = "contrato liveness inválido: $($response.Content)"
            return $false
        }
        return $true
    } catch {
        $script:LastControllerLivenessDiagnostic = $_.Exception.Message
        if ([string]::IsNullOrWhiteSpace($script:LastControllerLivenessDiagnostic)) {
            $script:LastControllerLivenessDiagnostic = $script:LastRuntimeHttpProbeDiagnostic
        }
        return $false
    }
}

function Test-ControllerSafety {
    # Detailed safety/operational diagnostics may be slow. A failure here keeps
    # the process alive but marks ATTENTION; only failed liveness can restart it.
    $script:LastControllerSafetyDiagnostic = ''
    try {
        $response = Invoke-RuntimeHttpProbe -Uri $healthUrl -TimeoutSeconds 8
        if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 300) {
            $script:LastControllerSafetyDiagnostic = "health detalhado retornou HTTP $($response.StatusCode)"
            return $false
        }

        $payload = $response.Content | ConvertFrom-Json
        if ($payload.ok -ne $true) { $script:LastControllerSafetyDiagnostic = 'health detalhado não confirmou ok=true'; return $false }
        if ($payload.execution_allowed -ne $false) { $script:LastControllerSafetyDiagnostic = 'execution_allowed não está bloqueado'; return $false }
        if ($payload.real -ne 'DESABILITADO') { $script:LastControllerSafetyDiagnostic = 'REAL não está declarado DESABILITADO'; return $false }

        $op = $payload.operational_observability.execution
        if ($null -eq $op) { $script:LastControllerSafetyDiagnostic = 'observabilidade operacional de execução ausente'; return $false }
        if ($op.allowed -ne $false) { $script:LastControllerSafetyDiagnostic = 'gate operacional não confirmou bloqueio'; return $false }
        if ($op.real -ne 'DISABLED') { $script:LastControllerSafetyDiagnostic = 'gate operacional não confirmou REAL desabilitado'; return $false }

        $realRuntime = $payload.real_runtime
        if ($null -eq $realRuntime) { $script:LastControllerSafetyDiagnostic = 'estado REAL independente ausente'; return $false }
        if ($realRuntime.real_execution_allowed -ne $false) { $script:LastControllerSafetyDiagnostic = 'runtime REAL não confirmou bloqueio'; return $false }
        if ($realRuntime.explicitly_enabled -ne $false) { $script:LastControllerSafetyDiagnostic = 'runtime REAL está explicitamente habilitado'; return $false }

        return $true
    } catch {
        $script:LastControllerSafetyDiagnostic = "diagnóstico detalhado indisponível: $($_.Exception.Message)"
        return $false
    }
}

function Test-SafeRepairAuthorization {
    param(
        [string]$Action,
        [int]$AttemptsUsed,
        [int]$MaxAttempts,
        [bool]$RequiresHumanSupervision = $false
    )
    $script:LastRepairAuthorizationDiagnostic = ''
    $now = Get-Date
    while ($restartTimes.Count -gt 0 -and $restartTimes[0] -lt $now.AddHours(-1)) {
        $restartTimes.RemoveAt(0)
    }
    $AttemptsUsed = $restartTimes.Count
    $cooldownElapsed = $true
    if ($restartTimes.Count -gt 0) {
        $cooldownElapsed = (($now - $restartTimes[$restartTimes.Count - 1]).TotalSeconds -ge $RestartDelaySeconds)
    }
    $maintenanceLockClear = -not (Test-Path -LiteralPath $maintenanceLockPath -PathType Leaf)
    $policyPath = Join-Path $ProjectRoot 'deployment\authorize_self_repair.py'
    if (-not (Test-Path -LiteralPath $policyPath -PathType Leaf)) {
        $script:LastRepairAuthorizationDiagnostic = 'política de autorreparo ausente; reparo bloqueado'
        return $false
    }
    try {
        $policyArgs = @(
            $policyPath,
            '--action', $Action,
            '--attempts-used', [string]$AttemptsUsed,
            '--max-attempts', [string]$MaxAttempts,
            '--local-only', 'true',
            '--reversible', 'true',
            '--deterministic', 'true',
            '--prevalidated', 'true',
            '--external-side-effects', 'false',
            '--touches-execution-state', 'false',
            '--requires-human-supervision', ([string]$RequiresHumanSupervision).ToLowerInvariant(),
            '--cooldown-elapsed', ([string]$cooldownElapsed).ToLowerInvariant(),
            '--maintenance-lock-clear', ([string]$maintenanceLockClear).ToLowerInvariant()
        )
        $policyOutput = & $PythonExe @policyArgs 2>&1
        $policyExitCode = $LASTEXITCODE
        $payload = ([string](@($policyOutput | ForEach-Object { [string]$_ } | Select-Object -Last 1))) | ConvertFrom-Json
        $script:LastRepairAuthorizationDiagnostic = [string]$payload.reason
        return ($policyExitCode -eq 0 -and $payload.allowed -eq $true)
    } catch {
        $script:LastRepairAuthorizationDiagnostic = "falha ao avaliar política de autorreparo: $($_.Exception.Message)"
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
    if (-not $script:RestartHistoryValid) {
        $reason = "Histórico de reinícios inválido; recuperação automática bloqueada até correção manual: $script:RestartHistoryError"
        Write-StartupLog $reason
        Write-SupervisorStatus 'ATTENTION' $reason
        while (-not (Test-Path -LiteralPath $stopPath -PathType Leaf)) {
            Start-Sleep -Seconds 30
        }
        $finalState = 'STOPPED'
        $finalReason = 'Parada controlada após bloqueio por histórico de reinícios inválido.'
        break
    }
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

    $process = $null
    if ($null -ne $existingController) {
        Write-StartupLog "Instância existente detectada (PID $($existingController.ProcessId)); verificando /api/health/live."
        if (Test-ControllerHealth) {
            $process = Get-Process -Id $existingController.ProcessId -ErrorAction Stop
            Write-SupervisorStatus 'STARTING' 'Instância existente responde ao liveness; validando segurança detalhada sem reinício automático.'
        } else {
            if (Test-SafeRepairAuthorization -Action 'restart_controller' -AttemptsUsed $restartTimes.Count -MaxAttempts $MaxRestartsPerHour) {
                Write-StartupLog "Instância existente não respondeu liveness; política autorizou encerramento para recuperação limpa."
                & taskkill.exe /PID $existingController.ProcessId /T /F 2>$null | Out-Null
                Start-Sleep -Seconds 2
            } else {
                Write-StartupLog "Instância existente não responde, mas o reparo foi bloqueado: $script:LastRepairAuthorizationDiagnostic"
                $process = Get-Process -Id $existingController.ProcessId -ErrorAction SilentlyContinue
                Write-SupervisorStatus 'ATTENTION' "Instância existente não responde ao liveness; reparo automático bloqueado: $script:LastRepairAuthorizationDiagnostic"
            }
        }
    }

    if ($null -eq $process) {
        if ($restartTimes.Count -gt 0 -and
            -not (Test-SafeRepairAuthorization -Action 'restart_controller' -AttemptsUsed $restartTimes.Count -MaxAttempts $MaxRestartsPerHour)) {
            Write-StartupLog "Nova inicialização automática do Controlador bloqueada pela política: $script:LastRepairAuthorizationDiagnostic"
            Write-SupervisorStatus 'ATTENTION' "Nova inicialização bloqueada pela política de autorreparo: $script:LastRepairAuthorizationDiagnostic"
            Start-Sleep -Seconds 30
            continue
        }
        Write-StartupLog 'Iniciando app.py sob supervisão.'
        if (Test-Path -LiteralPath $appStdoutPath) { Remove-Item -LiteralPath $appStdoutPath -Force -ErrorAction SilentlyContinue }
        if (Test-Path -LiteralPath $appStderrPath) { Remove-Item -LiteralPath $appStderrPath -Force -ErrorAction SilentlyContinue }

        $appPath = Join-Path $ProjectRoot 'app.py'
        $process = Start-Process -FilePath $PythonExe -ArgumentList @('-u', $appPath) -WorkingDirectory $ProjectRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput $appStdoutPath -RedirectStandardError $appStderrPath
        Write-SupervisorStatus 'STARTING' "app.py iniciado; aguardando /api/health (PID $($process.Id))."
    }

    $healthy = Wait-ControllerHealth -Process $process -WaitSeconds $HealthWaitSeconds
    if ($healthy) {
        Write-StartupLog "Controlador respondeu ao liveness (PID $($process.Id)); verificando segurança detalhada separadamente."
        $safetyReady = Test-ControllerSafety
        if ($safetyReady) {
            Write-SupervisorStatus 'HEALTHY' 'app.py ativo; liveness e health detalhado confirmados; REAL bloqueado.'
        } else {
            Write-StartupLog "Health detalhado requer atenção: $script:LastControllerSafetyDiagnostic"
            Write-SupervisorStatus 'ATTENTION' "app.py está vivo; health detalhado indisponível ou inseguro: $script:LastControllerSafetyDiagnostic. Execução permanece bloqueada."
        }
        $healthFailures = 0
        $safetyProbeCounter = 0
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
                Write-StartupLog "Liveness do Controlador falhou ($healthFailures/$HealthFailureThreshold) enquanto o processo permanecia ativo; detalhe=$script:LastControllerLivenessDiagnostic."
                if ($healthFailures -ge $HealthFailureThreshold) {
                    if (Test-SafeRepairAuthorization -Action 'restart_controller' -AttemptsUsed $restartTimes.Count -MaxAttempts $MaxRestartsPerHour) {
                        Write-StartupLog 'Liveness do Controlador permaneceu indisponível; política autorizou recuperação supervisionada.'
                        Stop-ControllerProcess -Process $process -Reason 'Liveness não respondeu; encerrando processo para recuperação limpa'
                        break
                    }
                    Write-StartupLog "Reparo automático do Controlador bloqueado pela política: $script:LastRepairAuthorizationDiagnostic"
                    Write-SupervisorStatus 'ATTENTION' "Liveness indisponível, mas reparo automático bloqueado: $script:LastRepairAuthorizationDiagnostic"
                    $healthFailures = 0
                    Start-Sleep -Seconds 30
                }
            }

            $safetyProbeCounter++
            if ($safetyProbeCounter -ge 10) {
                $safetyProbeCounter = 0
                $safetyReady = Test-ControllerSafety
                if ($safetyReady) {
                    Write-SupervisorStatus 'HEALTHY' 'app.py ativo; liveness e health detalhado confirmados; REAL bloqueado.'
                } else {
                    Write-StartupLog "Health detalhado requer atenção: $script:LastControllerSafetyDiagnostic"
                    Write-SupervisorStatus 'ATTENTION' "app.py está vivo; health detalhado indisponível ou inseguro: $script:LastControllerSafetyDiagnostic. Execução permanece bloqueada."
                }
            }
            Start-Sleep -Seconds $HealthPollSeconds
        }
        $appExitCode = if ($process.HasExited) { $process.ExitCode } else { -1 }
    } else {
        if (-not $process.HasExited) {
            if (Test-SafeRepairAuthorization -Action 'restart_controller' -AttemptsUsed $restartTimes.Count -MaxAttempts $MaxRestartsPerHour) {
                Stop-ControllerProcess -Process $process -Reason 'Liveness não respondeu durante inicialização; encerrando processo para recuperação limpa'
            } else {
                Write-StartupLog "Inicialização sem liveness, mas o reparo foi bloqueado: $script:LastRepairAuthorizationDiagnostic"
                Write-SupervisorStatus 'ATTENTION' "app.py não respondeu ao liveness; reparo automático bloqueado: $script:LastRepairAuthorizationDiagnostic"
                Start-Sleep -Seconds 30
                continue
            }
        }
        if (Test-Path -LiteralPath $appStdoutPath) { Get-Content -LiteralPath $appStdoutPath -ErrorAction SilentlyContinue | Add-Content -LiteralPath $logPath }
        if (Test-Path -LiteralPath $appStderrPath) { Get-Content -LiteralPath $appStderrPath -ErrorAction SilentlyContinue | Add-Content -LiteralPath $logPath }
        $appExitCode = if ($process.HasExited) { $process.ExitCode } else { -1 }
        Write-StartupLog "Controlador não alcançou /api/health/live; código observado=$appExitCode; detalhe=$script:LastControllerLivenessDiagnostic."
    }

    if (Test-Path -LiteralPath $stopPath -PathType Leaf) { break }

    $now = Get-Date
    while ($restartTimes.Count -gt 0 -and $restartTimes[0] -lt $now.AddHours(-1)) {
        $restartTimes.RemoveAt(0)
    }

    if ($restartTimes.Count -ge $MaxRestartsPerHour) {
        Write-StartupLog "Limite de reinícios atingido ($MaxRestartsPerHour/h). Controlador entra em espera controlada; o supervisor continuará ativo."
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
