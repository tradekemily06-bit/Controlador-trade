param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonExe = 'python',
    [string]$MetaEditorPath = '',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

function Copy-WithRetry([string]$Source, [string]$Destination, [int]$Attempts = 5) {
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            Copy-Item -LiteralPath $Source -Destination $Destination -Force -ErrorAction Stop
            return
        } catch {
            if ($attempt -eq $Attempts) { throw }
            Start-Sleep -Milliseconds (250 * $attempt)
        }
    }
}

function Restore-File([string]$Backup, [string]$Target) {
    if (Test-Path -LiteralPath $Backup -PathType Leaf) {
        Copy-WithRetry -Source $Backup -Destination $Target
    } elseif (Test-Path -LiteralPath $Target -PathType Leaf) {
        Remove-Item -LiteralPath $Target -Force -ErrorAction SilentlyContinue
    }
}

$source = Join-Path $ProjectRoot 'mql5\Experts\ControladorTrading\Controlador-Trading.mq5'
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
$destination = Join-Path $destinationDir 'Controlador-Trading.mq5'
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
if (Test-Path -LiteralPath $destination) { Copy-WithRetry -Source $destination -Destination $backupSource }
if (Test-Path -LiteralPath $binary) { Copy-WithRetry -Source $binary -Destination $backupBinary }

Copy-WithRetry -Source $source -Destination $destination

$log = [System.IO.Path]::ChangeExtension($destination, '.log')
if (Test-Path -LiteralPath $log) { Remove-Item -LiteralPath $log -Force }
$compileStartedAt = Get-Date
$explicitLog = $log

& $MetaEditorPath "/compile:$destination" "/log:$explicitLog" | Out-Null
Start-Sleep -Milliseconds 500

if (-not (Test-Path -LiteralPath $log -PathType Leaf)) {
    Restore-File -Backup $backupSource -Target $destination
    Restore-File -Backup $backupBinary -Target $binary
    throw "MetaEditor não produziu log de compilação: $log"
}

$logText = Get-Content -LiteralPath $log -Raw -ErrorAction SilentlyContinue
$errors = [regex]::Match($logText, '(?i)(\d+)\s+errors?').Groups[1].Value
$warnings = [regex]::Match($logText, '(?i)(\d+)\s+warnings?').Groups[1].Value
if ($errors -ne '0' -or $warnings -ne '0') {
    Restore-File -Backup $backupSource -Target $destination
    Restore-File -Backup $backupBinary -Target $binary
    throw "Compilação MQL5 rejeitada: errors=$errors warnings=$warnings. Log: $log"
}

if (-not (Test-Path -LiteralPath $binary -PathType Leaf)) {
    Restore-File -Backup $backupSource -Target $destination
    Restore-File -Backup $backupBinary -Target $binary
    throw "MetaEditor terminou sem gerar o EX5 esperado: $binary"
}

$binaryWriteTime = (Get-Item -LiteralPath $binary).LastWriteTime
if ($binaryWriteTime -lt $compileStartedAt.AddSeconds(-2)) {
    Restore-File -Backup $backupSource -Target $destination
    Restore-File -Backup $backupBinary -Target $binary
    throw "O EX5 não foi atualizado pela compilação: $binary"
}

Remove-Item -LiteralPath $log -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $backupSource -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $backupBinary -Force -ErrorAction SilentlyContinue

Write-Host "MQL5 sincronizado e compilado com sucesso."
Write-Host "Fonte: $source"
Write-Host "Destino: $destination"
Write-Host "MetaEditor: $MetaEditorPath"
