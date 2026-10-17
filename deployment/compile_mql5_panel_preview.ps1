param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$Mt5TerminalPath = 'C:\Program Files\MetaTrader 5\terminal64.exe',
    [string]$MetaEditorPath = '',
    [string]$Mt5DataPath = $env:CONTROLADOR_MT5_DATA_PATH
)

$ErrorActionPreference = 'Stop'

$source = Join-Path $ProjectRoot 'mql5\Experts\ControladorTrading\Controlador-Trading.mq5'
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Fonte MQL5 não encontrada: $source"
}

if (-not (Test-Path -LiteralPath $Mt5TerminalPath -PathType Leaf)) {
    throw "Terminal MT5 não encontrado: $Mt5TerminalPath"
}

$terminalInstallPath = Split-Path -Parent ([System.IO.Path]::GetFullPath($Mt5TerminalPath))
if ([string]::IsNullOrWhiteSpace($MetaEditorPath)) {
    foreach ($name in @('MetaEditor64.exe', 'metaeditor64.exe', 'metaeditor.exe')) {
        $candidate = Join-Path $terminalInstallPath $name
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $MetaEditorPath = $candidate
            break
        }
    }
}
if (-not (Test-Path -LiteralPath $MetaEditorPath -PathType Leaf)) {
    throw "MetaEditor não encontrado ao lado do terminal: $terminalInstallPath"
}

# Resolva a pasta de dados reportada pela instância MT5 acessada pela ponte.
# Não inferir o destino somente pelos arquivos existentes em perfis do Windows.
$pythonCode = @'
import json
import os
import sys
import MetaTrader5 as mt5
requested = sys.argv[1]
if not mt5.initialize(path=requested):
    raise SystemExit("MT5_INIT_FAILED:" + str(mt5.last_error()))
info = mt5.terminal_info()
if info is None:
    mt5.shutdown()
    raise SystemExit("MT5_TERMINAL_INFO_FAILED")
expected = os.path.normcase(os.path.realpath(requested))
actual = os.path.normcase(os.path.realpath(os.path.join(getattr(info, "path", ""), os.path.basename(requested))))
if actual != expected:
    mt5.shutdown()
    raise SystemExit("MT5_CONFIGURED_PATH_MISMATCH")
print(json.dumps({"path": getattr(info, "path", ""), "data_path": getattr(info, "data_path", "")}))
mt5.shutdown()
'@
$encodedPython = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($pythonCode))
$oneLinePython = "import base64;exec(compile(base64.b64decode('$encodedPython'),'<mt5-preview-path>','exec'))"
$bridgeResult = & python -c $oneLinePython $Mt5TerminalPath 2>$null
if ($LASTEXITCODE -ne 0 -or -not $bridgeResult) {
    throw 'Não foi possível confirmar a pasta de dados da instância MT5 pela ponte Python. Pré-visualização bloqueada.'
}
try { $bridgePaths = $bridgeResult | ConvertFrom-Json } catch {
    throw 'A ponte MT5 retornou dados de caminho inválidos. Pré-visualização bloqueada.'
}
if ([string]::IsNullOrWhiteSpace([string]$bridgePaths.data_path)) {
    throw 'A ponte MT5 não informou data_path. Pré-visualização bloqueada.'
}
$bridgeDataPath = [System.IO.Path]::GetFullPath([string]$bridgePaths.data_path)
if (-not (Test-Path -LiteralPath $bridgeDataPath -PathType Container) -or
    -not (Test-Path -LiteralPath (Join-Path $bridgeDataPath 'MQL5') -PathType Container)) {
    throw "A ponte MT5 retornou uma pasta de dados inválida: $bridgeDataPath"
}

if (-not [string]::IsNullOrWhiteSpace($Mt5DataPath)) {
    $requestedDataPath = [System.IO.Path]::GetFullPath($Mt5DataPath)
    if (-not [string]::Equals($requestedDataPath, $bridgeDataPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Destino de pré-visualização bloqueado: pasta configurada ($requestedDataPath) difere da instância MT5 conectada ($bridgeDataPath)."
    }
} else {
    $profilesRoot = Join-Path $env:APPDATA 'MetaQuotes\Terminal'
    $candidates = @()
    if (Test-Path -LiteralPath $profilesRoot -PathType Container) {
        foreach ($profile in @(Get-ChildItem -LiteralPath $profilesRoot -Directory -ErrorAction SilentlyContinue)) {
            $eaDir = Join-Path $profile.FullName 'MQL5\Experts\ControladorTrading'
            if ((Test-Path -LiteralPath (Join-Path $eaDir 'Controlador-Trading.mq5') -PathType Leaf) -or
                (Test-Path -LiteralPath (Join-Path $eaDir 'Controlador-Trading.ex5') -PathType Leaf)) {
                $candidates += [System.IO.Path]::GetFullPath($profile.FullName)
            }
        }
    }
    $candidates = @($candidates | Sort-Object -Unique)
    if ($candidates.Count -gt 1) {
        throw "Mais de uma pasta de dados MT5 contém o EA. Informe -Mt5DataPath correspondente à instância conectada: $($candidates -join '; ')"
    }
    if ($candidates.Count -eq 1 -and
        -not [string]::Equals($candidates[0], $bridgeDataPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Destino de pré-visualização bloqueado: a pasta com o EA ($($candidates[0])) difere da instância MT5 conectada ($bridgeDataPath)."
    }
}
$Mt5DataPath = $bridgeDataPath

$previewDir = Join-Path $Mt5DataPath 'MQL5\Experts\ControladorTradingPreview'
New-Item -ItemType Directory -Force -Path $previewDir | Out-Null
$previewSource = Join-Path $previewDir 'Controlador-Trading-Preview.mq5'
$previewBinary = [System.IO.Path]::ChangeExtension($previewSource, '.ex5')
$log = [System.IO.Path]::ChangeExtension($previewSource, '.log')
$provenance = "$previewBinary.provenance.json"

$sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
Copy-Item -LiteralPath $source -Destination $previewSource -Force
if ((Get-FileHash -LiteralPath $previewSource -Algorithm SHA256).Hash -ne $sourceHash) {
    throw 'A cópia de pré-visualização não corresponde à fonte versionada.'
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
if (Test-Path -LiteralPath $previewBinary -PathType Leaf) {
    Copy-Item -LiteralPath $previewBinary -Destination "$previewBinary.$stamp.bak" -Force
    Remove-Item -LiteralPath $previewBinary -Force
}
if (Test-Path -LiteralPath $provenance -PathType Leaf) {
    Copy-Item -LiteralPath $provenance -Destination "$provenance.$stamp.bak" -Force
    Remove-Item -LiteralPath $provenance -Force
}
if (Test-Path -LiteralPath $log -PathType Leaf) {
    Remove-Item -LiteralPath $log -Force
}

$compileStartedAt = Get-Date
& $MetaEditorPath "/compile:$previewSource" "/log:$log" | Out-Null
$metaEditorExitCode = $LASTEXITCODE
Start-Sleep -Milliseconds 500

if (-not (Test-Path -LiteralPath $log -PathType Leaf)) {
    throw "MetaEditor não produziu o log de compilação: $log"
}
$logText = Get-Content -LiteralPath $log -Raw -ErrorAction Stop
$errorMatch = [regex]::Match($logText, '(?i)(\d+)\s+(errors?|erros?)')
$warningMatch = [regex]::Match($logText, '(?i)(\d+)\s+(warnings?|avisos?)')
if (-not $errorMatch.Success -or -not $warningMatch.Success) {
    throw "Log sem contagem inequívoca de erros/avisos; revisão manual necessária: $log"
}
$errors = [int]$errorMatch.Groups[1].Value
$warnings = [int]$warningMatch.Groups[1].Value
if ($errors -ne 0 -or $warnings -ne 0) {
    throw "Pré-visualização não aprovada: errors=$errors warnings=$warnings. Log preservado: $log"
}
if (-not (Test-Path -LiteralPath $previewBinary -PathType Leaf)) {
    throw "MetaEditor não gerou o EX5 de pré-visualização esperado: $previewBinary"
}
$binaryItem = Get-Item -LiteralPath $previewBinary
if ($binaryItem.LastWriteTime -lt $compileStartedAt.AddSeconds(-2)) {
    throw "O EX5 de pré-visualização não foi atualizado nesta compilação: $previewBinary"
}

$provenancePayload = @{
    schema_version = 1
    purpose = 'visual-preview-only'
    source_sha256 = $sourceHash
    binary_sha256 = (Get-FileHash -LiteralPath $previewBinary -Algorithm SHA256).Hash
    compiled_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    installed_ea_replaced = $false
    real_execution_authorized = $false
}
$provenancePayload | ConvertTo-Json -Compress | Set-Content -LiteralPath $provenance -Encoding ASCII

Write-Host 'Pré-visualização MQL5 compilada com sucesso (0 erros, 0 avisos).'
Write-Host "EA de teste: $previewBinary"
Write-Host "Fonte de teste: $previewSource"
Write-Host "Proveniência: $provenance"
Write-Host 'O EA instalado não foi substituído. Abra o Navegador do MT5, atualize Experts e use ControladorTradingPreview apenas em gráfico DEMO para conferir o visual.'
if ($metaEditorExitCode -ne 0) {
    Write-Warning "MetaEditor retornou código $metaEditorExitCode; o log e o EX5 recém-gerado confirmaram a compilação."
}
