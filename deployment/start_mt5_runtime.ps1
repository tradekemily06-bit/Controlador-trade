param(
    [Parameter(Mandatory = $true)]
    [string]$Mt5TerminalPath
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Mt5TerminalPath -PathType Leaf)) {
    throw "MT5 terminal não encontrado: $Mt5TerminalPath"
}

$processName = [System.IO.Path]::GetFileNameWithoutExtension($Mt5TerminalPath)
if (-not (Get-Process -Name $processName -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $Mt5TerminalPath
}
