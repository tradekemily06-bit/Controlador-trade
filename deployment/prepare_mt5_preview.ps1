[CmdletBinding()]
param(
    [string]$ProjectRoot = 'C:\Users\Jose\Controlador-trade',
    [string]$TerminalDataPath = (Join-Path $env:APPDATA 'MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075'),
    [string]$MetaEditorPath = 'C:\Program Files\MetaTrader 5\MetaEditor64.exe',
    [string]$ExpectedBranch = 'fix/mt5-order-state-reconciliation-20261110'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
$TerminalDataPath = [System.IO.Path]::GetFullPath($TerminalDataPath)

# Refuse to preview an arbitrary or stale worktree. The source must come from
# the reviewed project repository, on the expected branch, with no local edits.
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git não está disponível no PATH; prévia cancelada para evitar compilar uma cópia não verificada.'
}
$gitRoot = (& git -C $ProjectRoot rev-parse --show-toplevel 2>$null | Select-Object -First 1)
if ($LASTEXITCODE -ne 0 -or -not $gitRoot) {
    throw 'A pasta selecionada não é uma cópia Git válida; prévia cancelada.'
}
$gitRoot = [System.IO.Path]::GetFullPath($gitRoot.Trim())
if ($gitRoot.TrimEnd([char]'\') -ne $ProjectRoot.TrimEnd([char]'\')) {
    throw "A raiz Git ($gitRoot) não corresponde à pasta selecionada ($ProjectRoot)."
}
$actualBranch = (& git -C $ProjectRoot branch --show-current 2>$null | Select-Object -First 1)
if ($LASTEXITCODE -ne 0 -or -not $actualBranch -or $actualBranch.Trim() -ne $ExpectedBranch) {
    throw "Branch incorreta para prévia. Esperada: $ExpectedBranch; encontrada: $actualBranch"
}
$actualCommit = (& git -C $ProjectRoot rev-parse HEAD 2>$null | Select-Object -First 1)
if ($LASTEXITCODE -ne 0 -or $actualCommit -notmatch '^[0-9a-f]{40}$') {
    throw 'Não foi possível identificar o commit exato da cópia de trabalho.'
}
$workingTree = (& git -C $ProjectRoot status --porcelain 2>$null)
if ($LASTEXITCODE -ne 0) {
    throw 'Não foi possível verificar o estado da cópia de trabalho.'
}
if ($workingTree) {
    throw 'A cópia de trabalho contém alterações locais ou arquivos não rastreados. Faça commit ou limpe a cópia antes da prévia.'
}
$origin = (& git -C $ProjectRoot remote get-url origin 2>$null | Select-Object -First 1)
if ($LASTEXITCODE -ne 0) {
    throw 'Não foi possível validar o repositório remoto origin.'
}
$normalizedOrigin = $origin.Trim().TrimEnd('/') -replace '\.git$', ''
$allowedOrigins = @(
    'https://github.com/tradekemily06-bit/Controlador-trade',
    'http://github.com/tradekemily06-bit/Controlador-trade',
    'git@github.com:tradekemily06-bit/Controlador-trade'
)
if ($normalizedOrigin -notin $allowedOrigins) {
    throw "Repositório remoto inesperado: $origin"
}

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
# Compile the exact source in the selected worktree (including the current PR branch).
# Never fetch or silently substitute a different branch: that could preview an older EA.
$sourceRelative = 'mql5\Experts\ControladorTrading\Controlador-Trading.mq5'
$sourcePath = Join-Path $ProjectRoot $sourceRelative
if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
    throw "Fonte MQL5 não encontrada na cópia de trabalho: $sourcePath"
}
$sourceHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash
$sourceText = [System.IO.File]::ReadAllText($sourcePath, [System.Text.Encoding]::UTF8)
if (-not $sourceText.Contains('string P="CTP_";')) {
    throw 'A fonte MQL5 não contém o identificador esperado; compilação de prévia cancelada.'
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
Write-Output "SOURCE_SHA256=$sourceHash"
Write-Output "SOURCE_BRANCH=$actualBranch"
Write-Output "SOURCE_COMMIT=$actualCommit"
Write-Output "PREVIEW_SOURCE=$previewSource"
Write-Output "PREVIEW_EX5=$previewBinary"
Write-Output "COMPILE_LOG=$compileLog"
Write-Output 'INSTALLED_EA_UNCHANGED=TRUE'
Write-Output 'REAL_EXECUTION=BLOCKED'
Write-Output 'Próximo passo: no MT5, atualize o Navegador e anexe Controlador-Trading-Preview a um gráfico DEMO separado. Não clique em RODAR CICLO DEMO durante a conferência visual.'
