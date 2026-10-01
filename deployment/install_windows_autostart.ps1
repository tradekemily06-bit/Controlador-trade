param(
    [string]$ProjectRoot = 'C:\Controlador-trade',
    [string]$PythonExe = 'python',
    [Parameter(Mandatory = $true)]
    [string]$Mt5TerminalPath,
    [string]$RuntimeDir = 'C:\Controlador-trade\.runtime',
    [string]$TaskPrefix = 'ControladorTrading'
)

$ErrorActionPreference = 'Stop'

$currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Execute este instalador uma única vez em um PowerShell como Administrador.'
}

$mt5Script = Join-Path $ProjectRoot 'deployment\start_mt5_runtime.ps1'
$controllerScript = Join-Path $ProjectRoot 'deployment\start_controlador_runtime.ps1'

foreach ($path in @($mt5Script, $controllerScript)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Arquivo de inicialização não encontrado: $path"
    }
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

$principalTask = New-ScheduledTaskPrincipal -UserId $currentIdentity.Name -LogonType InteractiveToken -RunLevel Highest
$mt5Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $mt5Script + '" -Mt5TerminalPath "' + $Mt5TerminalPath + '"'
$controllerArguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $controllerScript + '" -ProjectRoot "' + $ProjectRoot + '" -PythonExe "' + $PythonExe + '" -RuntimeDir "' + $RuntimeDir + '"'

$mt5Action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $mt5Arguments
$controllerAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $controllerArguments
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentIdentity.Name

Register-ScheduledTask -TaskName "$TaskPrefix-MT5" -Action $mt5Action -Trigger $trigger -Principal $principalTask -Description 'Inicia o MetaTrader 5 usado pelo Controlador Trading.' -Force | Out-Null
Register-ScheduledTask -TaskName "$TaskPrefix-Controlador" -Action $controllerAction -Trigger $trigger -Principal $principalTask -Description 'Inicia o Controlador Trading e aguarda o MT5 DEMO.' -Force | Out-Null

Write-Host 'Inicialização automática instalada para a sessão Windows atual.'
Write-Host 'MT5 e Controlador serão iniciados no logon; o Controlador faz preflight DEMO antes de operar.'
Write-Host 'Nenhuma senha, token ou credencial foi gravada por este instalador.'
