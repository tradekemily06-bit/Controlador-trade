param(
    [string]$ProjectRoot = 'C:\Controlador-trade',
    [string]$PythonExe = 'python',
    [string]$RuntimeDir = '',
    [int]$Mt5WaitSeconds = 180
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RuntimeDir)) { $RuntimeDir = Join-Path $ProjectRoot '.runtime' }

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
$logPath = Join-Path $RuntimeDir 'controlador-startup.log'

function Write-StartupLog([string]$Message) {
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -LiteralPath $logPath -Value "$timestamp $Message"
}

Set-Location $ProjectRoot
Write-StartupLog 'Iniciando pré-verificação do MT5 DEMO.'
$deadline = (Get-Date).AddSeconds($Mt5WaitSeconds)
$demoReady = $false
while ((Get-Date) -lt $deadline) {
    try {
        & $PythonExe -c "import MetaTrader5 as mt5; from execution.mt5_demo_runtime_preflight import run_preflight; r=run_preflight(mt5); raise SystemExit(0 if r.available and r.demo else 1)"
        if ($LASTEXITCODE -eq 0) { $demoReady = $true; break }
    } catch {}
    Start-Sleep -Seconds 5
}
if ($demoReady) {
    Write-StartupLog 'MT5 DEMO confirmado; iniciando Controlador.'
} else {
    Write-StartupLog 'MT5 DEMO ainda não confirmado; iniciando Controlador mesmo assim. A execução deve permanecer bloqueada até o preflight/risk gate ficar válido.'
}
Write-StartupLog 'Pré-verificação concluída; iniciando app.py.'
& $PythonExe -u (Join-Path $ProjectRoot 'app.py') >> $logPath 2>&1
$appExitCode = $LASTEXITCODE
Write-StartupLog "Controlador finalizado com código de saída $appExitCode."
exit $appExitCode
