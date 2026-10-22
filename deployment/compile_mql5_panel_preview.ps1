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

if ([string]::IsNullOrWhiteSpace($Mt5DataPath)) {
    $profilesRoot = Join-Path $env:APPDATA 'MetaQuotes\Terminal'
    $candidates = @()
    if (Test-Path -LiteralPath $profilesRoot -PathType Container) {
        foreach ($profile in @(Get-ChildItem -LiteralPath $profilesRoot -Directory -ErrorAction SilentlyContinue)) {
            $eaDir = Join-Path $profile.FullName 'MQL5\Experts\ControladorTrading'
            if ((Test-Path -LiteralPath (Join-Path $eaDir 'Controlador-Trading.mq5') -PathType Leaf) -or
                (Test-Path -LiteralPath (Join-Path $eaDir 'Controlador-Trading.ex5') -PathType Leaf)) {
                $candidates += $profile.FullName
            }
        }
    }
    $candidates = @($candidates | Sort-Object -Unique)
    if ($candidates.Count -ne 1) {
        throw "Não foi possível escolher uma única pasta de dados MT5 com o EA existente. Informe -Mt5DataPath ou defina CONTROLADOR_MT5_DATA_PATH. Candidatas: $($candidates -join '; ')"
    }
    $Mt5DataPath = $candidates[0]
}

$Mt5DataPath = [System.IO.Path]::GetFullPath($Mt5DataPath)
if (-not (Test-Path -LiteralPath (Join-Path $Mt5DataPath 'MQL5') -PathType Container)) {
    throw "Pasta de dados MT5 inválida (MQL5 ausente): $Mt5DataPath"
}

$previewDir = Join-Path $Mt5DataPath 'MQL5\Experts\ControladorTrading_PAINEL_APROVADO_VALIDACAO'
New-Item -ItemType Directory -Force -Path $previewDir | Out-Null
$previewSource = Join-Path $previewDir 'Controlador-Trading-Painel-Aprovado.mq5'
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
Write-Host 'O EA instalado não foi substituído. Abra o Navegador do MT5, atualize Experts e use ControladorTrading_PAINEL_APROVADO_VALIDACAO apenas em gráfico DEMO para conferir o visual.'
if ($metaEditorExitCode -ne 0) {
    Write-Warning "MetaEditor retornou código $metaEditorExitCode; o log e o EX5 recém-gerado confirmaram a compilação."
}
