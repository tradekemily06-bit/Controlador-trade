param(
    [string]$ProjectRoot = 'C:\Controlador-trade',
    [string]$PythonExe = 'python',
    [Parameter(Mandatory = $true)]
    [string]$Mt5TerminalPath,
    [string]$RuntimeDir = '',
    [string]$TaskPrefix = 'ControladorTrading'
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($RuntimeDir)) {
    $RuntimeDir = Join-Path $ProjectRoot '.runtime'
}

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

$principalTask = New-ScheduledTaskPrincipal -UserId $currentIdentity.Name -LogonType Interactive -RunLevel Highest
$mt5Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $mt5Script + '" -Mt5TerminalPath "' + $Mt5TerminalPath + '" -RuntimeDir "' + $RuntimeDir + '"'
$controllerArguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $controllerScript + '" -ProjectRoot "' + $ProjectRoot + '" -PythonExe "' + $PythonExe + '" -RuntimeDir "' + $RuntimeDir + '"'

$mt5Action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $mt5Arguments
$controllerAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $controllerArguments
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentIdentity.Name
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

Register-ScheduledTask -TaskName "$TaskPrefix-MT5" -Action $mt5Action -Trigger $trigger -Principal $principalTask -Settings $settings -Description 'Supervisiona o MetaTrader 5 usado pelo Controlador Trading.' -Force | Out-Null
Register-ScheduledTask -TaskName "$TaskPrefix-Controlador" -Action $controllerAction -Trigger $trigger -Principal $principalTask -Settings $settings -Description 'Supervisiona o Controlador Trading e aguarda o MT5 DEMO.' -Force | Out-Null

Write-Host 'Inicialização automática instalada para a sessão Windows atual.'
Write-Host 'MT5 e Controlador serão iniciados no logon e supervisionados; quedas são recuperadas com limite e backoff.'
Write-Host 'Nenhuma senha, token ou credencial foi gravada por este instalador.'
