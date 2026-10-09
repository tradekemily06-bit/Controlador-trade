param(
    [string]$ProjectRoot = 'C:\Controlador-trade',
    [string]$PythonExe = 'python',
    [string]$RuntimeDir = '',
    [string]$Mt5TerminalPath = 'C:\Program Files\MetaTrader 5\terminal64.exe',
    [string]$TaskPrefix = 'ControladorTrading'
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RuntimeDir)) { $RuntimeDir = Join-Path $ProjectRoot '.runtime' }
if ($PythonExe -eq 'python' -or $PythonExe -eq 'python.exe') {
    $resolvedPython = Get-Command $PythonExe -ErrorAction SilentlyContinue
    if ($null -eq $resolvedPython -or [string]::IsNullOrWhiteSpace($resolvedPython.Source)) { throw 'Python não foi encontrado no PATH.' }
    $PythonExe = $resolvedPython.Source
}
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) { throw "Python não encontrado: $PythonExe" }
if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) { throw "Projeto não encontrado: $ProjectRoot" }

$checks = New-Object System.Collections.Generic.List[object]
function Add-Check([string]$Name, [bool]$Ok, [string]$Detail) { $checks.Add([pscustomobject]@{check=$Name; ok=$Ok; detail=$Detail}) }
function Has-File([string]$Path) { return Test-Path -LiteralPath $Path -PathType Leaf }

foreach ($relative in @('app.py','deployment\start_controlador_runtime.ps1','deployment\start_mt5_runtime.ps1','deployment\install_windows_autostart.ps1','deployment\sync_mql5_panel.ps1','deployment\bootstrap_windows_runtime.ps1')) {
    $path = Join-Path $ProjectRoot $relative
    Add-Check "arquivo:$relative" (Has-File $path) $path
}
Add-Check 'python' $true $PythonExe

Push-Location $ProjectRoot
try {
    & $PythonExe -c 'import execution, MetaTrader5; print("imports=OK")' | Out-Null
    Add-Check 'python-imports' ($LASTEXITCODE -eq 0) 'execution + MetaTrader5'

    $health = $false
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 3 -ErrorAction Stop
        $payload = $response.Content | ConvertFrom-Json
        $op = $payload.operational_observability.execution
        $realRuntime = $payload.real_runtime
        $health = (
            $response.StatusCode -ge 200 -and
            $response.StatusCode -lt 300 -and
            $payload.ok -eq $true -and
            $payload.execution_allowed -eq $false -and
            $payload.real -eq 'DESABILITADO' -and
            $null -ne $op -and
            $op.allowed -eq $false -and
            $op.real -eq 'DISABLED' -and
            $null -ne $realRuntime -and
            $realRuntime.real_execution_allowed -eq $false -and
            $realRuntime.explicitly_enabled -eq $false
        )
        Add-Check 'controller-health-safe' $health "HTTP=$($response.StatusCode); execution_allowed=$($payload.execution_allowed); real=$($payload.real); operational.allowed=$($op.allowed); operational.real=$($op.real); real_runtime.allowed=$($realRuntime.real_execution_allowed); real_runtime.explicitly_enabled=$($realRuntime.explicitly_enabled)"
    } catch { Add-Check 'controller-health-safe' $false 'http://127.0.0.1:8000/api/health não respondeu com contrato canônico seguro.' }

    $mt5Healthy = $false
    try {
        & $PythonExe -c 'import os,sys,MetaTrader5 as mt5; expected=os.path.normcase(os.path.dirname(os.path.realpath(sys.argv[1]))); ok=mt5.initialize(path=sys.argv[1]); t=mt5.terminal_info() if ok else None; a=mt5.account_info() if ok else None; d=getattr(mt5,"ACCOUNT_TRADE_MODE_DEMO",None); actual=os.path.normcase(os.path.realpath(getattr(t,"path",""))) if t else ""; h=ok and t is not None and bool(getattr(t,"connected",False)) and actual==expected and a is not None and d is not None and getattr(a,"trade_mode",None)==d; print("MT5_HEALTH="+str(h)); mt5.shutdown(); raise SystemExit(0 if h else 1)' $Mt5TerminalPath | Out-Null
        $mt5Healthy = $LASTEXITCODE -eq 0
    } catch {}
    Add-Check 'mt5-demo-health' $mt5Healthy 'terminal conectado + conta DEMO; disponibilidade de mercado é verificada separadamente.'
} finally { Pop-Location }

Add-Check 'mt5-terminal-file' (Has-File $Mt5TerminalPath) $Mt5TerminalPath
foreach ($task in @("$TaskPrefix-MT5","$TaskPrefix-Controlador")) {
    $exists = $false
    try { $null = Get-ScheduledTask -TaskName $task -ErrorAction Stop; $exists = $true } catch {}
    Add-Check "scheduled-task:$task" $exists $task
}

$mq5 = Join-Path $ProjectRoot 'mql5\Experts\ControladorTrading\Controlador-Trading.mq5'
Add-Check 'mql5-source' (Has-File $mq5) $mq5
if (Has-File $mq5) {
    try {
        $mt5Data = & $PythonExe -c 'import os,sys,MetaTrader5 as mt5; expected=os.path.normcase(os.path.dirname(os.path.realpath(sys.argv[1]))); ok=mt5.initialize(path=sys.argv[1]); i=mt5.terminal_info() if ok else None; actual=os.path.normcase(os.path.realpath(getattr(i,"path",""))) if i else ""; print(getattr(i,"data_path","") if i else ""); mt5.shutdown(); raise SystemExit(0 if ok and i and actual==expected else 1)' $Mt5TerminalPath 2>$null
        $dataPath = ($mt5Data | Select-Object -Last 1).Trim()
        if ($LASTEXITCODE -eq 0 -and $dataPath) {
            $ex5 = Join-Path $dataPath 'MQL5\Experts\ControladorTrading\Controlador-Trading.ex5'
            Add-Check 'mql5-ex5' (Has-File $ex5) $ex5
            if (Has-File $ex5) { Add-Check 'mql5-ex5-current' ((Get-Item $ex5).LastWriteTime -ge (Get-Item $mq5).LastWriteTime) "EX5=$((Get-Item $ex5).LastWriteTime); MQ5=$((Get-Item $mq5).LastWriteTime)" }
        } else { Add-Check 'mql5-ex5' $false 'Não foi possível obter o data_path do MT5 conectado.' }
    } catch { Add-Check 'mql5-ex5' $false $_.Exception.Message }
}

$failed = @($checks | Where-Object { -not $_.ok })
$summary = [pscustomobject]@{ generated_at=(Get-Date).ToUniversalTime().ToString('o'); project_root=$ProjectRoot; python=$PythonExe; runtime_dir=$RuntimeDir; checks=$checks; passed=($checks.Count-$failed.Count); failed=$failed.Count; ready=($failed.Count -eq 0) }
$summary | ConvertTo-Json -Depth 6
if ($failed.Count -gt 0) { exit 2 }
exit 0
