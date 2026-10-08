param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonExe = 'python',
    [string]$MetaEditorPath = '',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$source = Join-Path $ProjectRoot 'mql5\Experts\ControladorTrading\ControladorTradingPanel.mq5'
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Fonte MQL5 não encontrada: $source"
}

function Get-Mt5Paths {
    $code = @'
import json
import MetaTrader5 as mt5
if not mt5.initialize():
    raise SystemExit("MT5_INIT_FAILED:" + str(mt5.last_error()))
info = mt5.terminal_info()
if info is None:
    raise SystemExit("MT5_TERMINAL_INFO_FAILED")
print(json.dumps({
    "path": getattr(info, "path", ""),
    "data_path": getattr(info, "data_path", "")
}))
mt5.shutdown()
'@
    $result = & $PythonExe -c $code 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $result) { return $null }
    try { return ($result | ConvertFrom-Json) } catch { return $null }
}

$paths = Get-Mt5Paths
if (-not $paths -or [string]::IsNullOrWhiteSpace($paths.data_path)) {
    throw 'Não foi possível obter o data_path do MT5 conectado.'
}

$dataPath = [string]$paths.data_path
$destinationDir = Join-Path $dataPath 'MQL5\Experts\ControladorTrading'
$destination = Join-Path $destinationDir 'ControladorTradingPanel.mq5'
New-Item -ItemType Directory -Force -Path $destinationDir | Out-Null

if ([string]::IsNullOrWhiteSpace($MetaEditorPath)) {
    $candidate = Join-Path ([string]$paths.path) 'metaeditor64.exe'
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $MetaEditorPath = $candidate
    } else {
        $candidate = Join-Path ([string]$paths.path) 'metaeditor.exe'
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { $MetaEditorPath = $candidate }
    }
}
if (-not (Test-Path -LiteralPath $MetaEditorPath -PathType Leaf)) {
    throw 'MetaEditor não encontrado ao lado do terminal conectado.'
}

$sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
$destinationHash = if (Test-Path -LiteralPath $destination -PathType Leaf) { (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash } else { '' }

if (-not $Force -and $sourceHash -eq $destinationHash) {
    Write-Host "MQL5 já sincronizado: $destination"
    exit 0
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupSource = "$destination.$stamp.bak"
$backupBinary = [System.IO.Path]::ChangeExtension($destination, '.ex5') + ".$stamp.bak"
$binary = [System.IO.Path]::ChangeExtension($destination, '.ex5')
if (Test-Path -LiteralPath $destination) { Copy-Item -LiteralPath $destination -Destination $backupSource -Force }
if (Test-Path -LiteralPath $binary) { Copy-Item -LiteralPath $binary -Destination $backupBinary -Force }

Copy-Item -LiteralPath $source -Destination $destination -Force

$log = [System.IO.Path]::ChangeExtension($destination, '.log')
if (Test-Path -LiteralPath $log) { Remove-Item -LiteralPath $log -Force }

& $MetaEditorPath "/compile:$destination" /log | Out-Null
Start-Sleep -Milliseconds 500

if (-not (Test-Path -LiteralPath $log -PathType Leaf)) {
    if (Test-Path -LiteralPath $backupSource) { Copy-Item -LiteralPath $backupSource -Destination $destination -Force }
    throw "MetaEditor não produziu log de compilação: $log"
}

$logText = Get-Content -LiteralPath $log -Raw -ErrorAction SilentlyContinue
$errors = [regex]::Match($logText, '(?i)(\d+)\s+errors?').Groups[1].Value
$warnings = [regex]::Match($logText, '(?i)(\d+)\s+warnings?').Groups[1].Value
if ($errors -ne '0' -or $warnings -ne '0') {
    if (Test-Path -LiteralPath $backupSource) { Copy-Item -LiteralPath $backupSource -Destination $destination -Force }
    if (Test-Path -LiteralPath $backupBinary) { Copy-Item -LiteralPath $backupBinary -Destination $binary -Force } elseif (Test-Path -LiteralPath $binary) { Remove-Item -LiteralPath $binary -Force }
    throw "Compilação MQL5 rejeitada: errors=$errors warnings=$warnings. Log: $log"
}

Remove-Item -LiteralPath $log -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $backupSource -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $backupBinary -Force -ErrorAction SilentlyContinue

Write-Host "MQL5 sincronizado e compilado com sucesso."
Write-Host "Fonte: $source"
Write-Host "Destino: $destination"
Write-Host "MetaEditor: $MetaEditorPath"
