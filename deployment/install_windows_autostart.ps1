param(
    [string]$ProjectRoot = 'C:\Controlador-trade',
    [string]$PythonExe = 'python',
    [Parameter(Mandatory = $true)]
    [string]$Mt5TerminalPath,
    [string]$RuntimeDir = '',
    [string]$TaskPrefix = 'ControladorTrading',
    [ValidateSet('Interactive', 'AtStartupS4U')]
    [string]$AutostartMode = 'Interactive'
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
$syncScript = Join-Path $ProjectRoot 'deployment\sync_mql5_panel.ps1'

foreach ($path in @($mt5Script, $controllerScript, $syncScript)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Arquivo de inicialização não encontrado: $path"
    }
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

if ($AutostartMode -eq 'AtStartupS4U') {
    $principalTask = New-ScheduledTaskPrincipal -UserId $currentIdentity.Name -LogonType S4U -RunLevel Highest
    $trigger = New-ScheduledTaskTrigger -AtStartup
} else {
    $principalTask = New-ScheduledTaskPrincipal -UserId $currentIdentity.Name -LogonType Interactive -RunLevel Highest
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentIdentity.Name
}
$mt5Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $mt5Script + '" -Mt5TerminalPath "' + $Mt5TerminalPath + '" -RuntimeDir "' + $RuntimeDir + '"'
$controllerArguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $controllerScript + '" -ProjectRoot "' + $ProjectRoot + '" -PythonExe "' + $PythonExe + '" -RuntimeDir "' + $RuntimeDir + '"'

$mt5Action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $mt5Arguments
$controllerAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $controllerArguments
$syncArguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $syncScript + '" -ProjectRoot "' + $ProjectRoot + '" -PythonExe "' + $PythonExe + '"'
$syncAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $syncArguments
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

Register-ScheduledTask -TaskName "$TaskPrefix-MT5" -Action $mt5Action -Trigger $trigger -Principal $principalTask -Settings $settings -Description 'Supervisiona o MetaTrader 5 usado pelo Controlador Trading.' -Force | Out-Null
Register-ScheduledTask -TaskName "$TaskPrefix-Controlador" -Action $controllerAction -Trigger $trigger -Principal $principalTask -Settings $settings -Description 'Supervisiona o Controlador Trading e aguarda o MT5 DEMO.' -Force | Out-Null
Register-ScheduledTask -TaskName "$TaskPrefix-MT5-Sync" -Action $syncAction -Trigger $trigger -Principal $principalTask -Settings $settings -Description 'Sincroniza e compila automaticamente o painel MQL5 do Controlador Trading.' -Force | Out-Null

if ($AutostartMode -eq 'AtStartupS4U') {
    Write-Host 'Inicialização 24/7 configurada para iniciar no boot sem depender de logon interativo (S4U).'
    Write-Host 'A compatibilidade do MT5 com esta sessão não-interativa ainda deve ser validada no host de produção antes de operar.'
} else {
    Write-Host 'Inicialização automática instalada para a sessão Windows atual (modo interativo).'
    Write-Host 'Este modo NÃO garante operação após logoff/reboot sem novo logon; use -AutostartMode AtStartupS4U no host 24/7 após validar o MT5.'
}
Write-Host 'MT5 e Controlador serão supervisionados; quedas são recuperadas com limite e backoff.'
Write-Host 'O painel MQL5 é sincronizado e compilado automaticamente a partir do repositório local; não é necessário copiar o .mq5 manualmente para o MetaEditor.'
Write-Host 'Nenhuma senha, token ou credencial foi gravada por este instalador.'
