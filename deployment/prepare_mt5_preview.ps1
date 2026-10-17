[CmdletBinding()]
param(
    [string]$ProjectRoot = 'C:\Users\Jose\Controlador-trade',
    [string]$TerminalDataPath = (Join-Path $env:APPDATA 'MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075'),
    [string]$MetaEditorPath = 'C:\Program Files\MetaTrader 5\MetaEditor64.exe'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
$TerminalDataPath = [System.IO.Path]::GetFullPath($TerminalDataPath)

if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
    throw "Pasta do projeto não encontrada: $ProjectRoot"
}
if (-not (Test-Path -LiteralPath $TerminalDataPath -PathType Container) -or
    -not (Test-Path -LiteralPath (Join-Path $TerminalDataPath 'MQL5') -PathType Container)) {
    throw "Pasta de dados do MT5 não encontrada; prévia cancelada: $TerminalDataPath"
}
if (-not (Test-Path -LiteralPath $MetaEditorPath -PathType Leaf)) {
    throw "MetaEditor não encontrado: $MetaEditorPath"
}
$git = Get-Command git -ErrorAction SilentlyContinue
if ($null -eq $git) { throw 'Git não encontrado no PATH.' }

# Fetch only the remote reference. Do not checkout, merge, reset, or alter the user's worktree.
& $git.Source -C $ProjectRoot fetch origin main
if ($LASTEXITCODE -ne 0) { throw 'Não foi possível atualizar origin/main; nenhum EA foi alterado.' }

$sourceRelative = 'mql5/Experts/ControladorTrading/Controlador-Trading.mq5'
$sourceLines = & $git.Source -C $ProjectRoot show "origin/main:$sourceRelative"
if ($LASTEXITCODE -ne 0 -or $null -eq $sourceLines) {
    throw 'Não foi possível ler a fonte aprovada de origin/main.'
}
$nl = [System.Environment]::NewLine
$sourceText = ($sourceLines -join $nl) + $nl
if (-not $sourceText.Contains('string P="CTP_";')) {
    throw 'A fonte não corresponde à versão esperada; compilação de prévia cancelada.'
}

# A prefixo isolado impede que os objetos do preview colidam com o EA já instalado.
$sourceText = $sourceText.Replace('string P="CTP_";', 'string P="CTPREVIEW_";')
if ($sourceText.Contains('string P="CTP_";')) {
    throw 'Não foi possível isolar os objetos do preview.'
}

$installedFolder = Join-Path $TerminalDataPath 'MQL5\Experts\ControladorTrading'
$installedSource = Join-Path $installedFolder 'Controlador-Trading.mq5'
$installedBinary = Join-Path $installedFolder 'Controlador-Trading.ex5'
$installedSourceHash = if (Test-Path -LiteralPath $installedSource -PathType Leaf) {
    (Get-FileHash -LiteralPath $installedSource -Algorithm SHA256).Hash
} else { 'ABSENT' }
$installedBinaryHash = if (Test-Path -LiteralPath $installedBinary -PathType Leaf) {
    (Get-FileHash -LiteralPath $installedBinary -Algorithm SHA256).Hash
} else { 'ABSENT' }

$previewFolder = Join-Path $TerminalDataPath 'MQL5\Experts\ControladorTradingPreview'
New-Item -ItemType Directory -Force -Path $previewFolder | Out-Null
$previewSource = Join-Path $previewFolder 'Controlador-Trading-Preview.mq5'
$previewBinary = Join-Path $previewFolder 'Controlador-Trading-Preview.ex5'
$compileLog = Join-Path $previewFolder 'Controlador-Trading-Preview.compile.log'

[System.IO.File]::WriteAllText($previewSource, $sourceText, ([System.Text.UTF8Encoding]::new($false)))
if (Test-Path -LiteralPath $previewBinary -PathType Leaf) {
    Remove-Item -LiteralPath $previewBinary -Force
}
if (Test-Path -LiteralPath $compileLog -PathType Leaf) {
    Remove-Item -LiteralPath $compileLog -Force
}

$arguments = '/compile:"{0}" /log:"{1}"' -f $previewSource, $compileLog
$compiler = Start-Process -FilePath $MetaEditorPath -ArgumentList $arguments -Wait -PassThru
if (-not (Test-Path -LiteralPath $compileLog -PathType Leaf)) {
    throw "MetaEditor não gerou o log de compilação. Código de saída: $($compiler.ExitCode)"
}
$logText = Get-Content -LiteralPath $compileLog -Raw
if ($logText -match '(?im)\b[1-9]\d*\s+errors?\b') {
    throw "A prévia MQL5 não compilou. Consulte: $compileLog"
}
if ($logText -notmatch '(?im)\b0\s+errors?\b' -or -not (Test-Path -LiteralPath $previewBinary -PathType Leaf)) {
    throw "Não foi possível confirmar compilação sem erros. Consulte: $compileLog"
}

$installedSourceHashAfter = if (Test-Path -LiteralPath $installedSource -PathType Leaf) {
    (Get-FileHash -LiteralPath $installedSource -Algorithm SHA256).Hash
} else { 'ABSENT' }
$installedBinaryHashAfter = if (Test-Path -LiteralPath $installedBinary -PathType Leaf) {
    (Get-FileHash -LiteralPath $installedBinary -Algorithm SHA256).Hash
} else { 'ABSENT' }
if ($installedSourceHash -ne $installedSourceHashAfter -or $installedBinaryHash -ne $installedBinaryHashAfter) {
    throw 'A verificação detectou mudança na fonte/binário instalado. Não abra o preview até investigar.'
}

Write-Output 'PREVIEW_COMPILE=OK'
Write-Output "PREVIEW_SOURCE=$previewSource"
Write-Output "PREVIEW_EX5=$previewBinary"
Write-Output "COMPILE_LOG=$compileLog"
Write-Output 'INSTALLED_EA_UNCHANGED=TRUE'
Write-Output 'REAL_EXECUTION=BLOCKED'
Write-Output 'Próximo passo: no MT5, atualize o Navegador e anexe Controlador-Trading-Preview a um gráfico DEMO separado. Não clique em RODAR CICLO DEMO durante a conferência visual.'
