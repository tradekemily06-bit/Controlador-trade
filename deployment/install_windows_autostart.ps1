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

if ($PythonExe -eq 'python' -or $PythonExe -eq 'python.exe') {
    $resolvedPython = Get-Command $PythonExe -ErrorAction SilentlyContinue
    if ($null -eq $resolvedPython -or [string]::IsNullOrWhiteSpace($resolvedPython.Source)) {
        throw "Python não foi encontrado no PATH. Informe -PythonExe com o caminho completo do python.exe."
    }
    $PythonExe = $resolvedPython.Source
}
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Python não encontrado: $PythonExe"
}
if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
    throw "Diretório do projeto não encontrado: $ProjectRoot"
}
$machineIdentity = [Environment]::GetEnvironmentVariable('CONTROLADOR_SINGLE_USER_IDENTITY', 'Machine')
if ([string]::IsNullOrWhiteSpace([string]$machineIdentity)) {
    throw 'Defina CONTROLADOR_SINGLE_USER_IDENTITY no escopo de Máquina do Windows antes de instalar as tarefas. Use exatamente a identidade individual permitida no Cloudflare Access.'
}
if (-not [string]::Equals([string]$env:CONTROLADOR_SINGLE_USER_IDENTITY, [string]$machineIdentity, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'A identidade do processo não corresponde à identidade persistida no escopo de Máquina. Abra um novo PowerShell elevado após definir a variável.'
}
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
$streamlitScript = Join-Path $ProjectRoot 'deployment\start_streamlit_panel.ps1'

foreach ($path in @($mt5Script, $controllerScript, $streamlitScript)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Arquivo de inicialização não encontrado: $path"
    }
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
Write-Host "Python do runtime: $PythonExe"

if ($AutostartMode -eq 'AtStartupS4U') {
    $principalTask = New-ScheduledTaskPrincipal -UserId $currentIdentity.Name -LogonType S4U -RunLevel Highest
    $trigger = New-ScheduledTaskTrigger -AtStartup
} else {
    $principalTask = New-ScheduledTaskPrincipal -UserId $currentIdentity.Name -LogonType Interactive -RunLevel Highest
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentIdentity.Name
}
$mt5Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $mt5Script + '" -Mt5TerminalPath "' + $Mt5TerminalPath + '" -ProjectRoot "' + $ProjectRoot + '" -PythonExe "' + $PythonExe + '" -RuntimeDir "' + $RuntimeDir + '"'
$controllerArguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $controllerScript + '" -ProjectRoot "' + $ProjectRoot + '" -PythonExe "' + $PythonExe + '" -RuntimeDir "' + $RuntimeDir + '" -Mt5TerminalPath "' + $Mt5TerminalPath + '"'
$streamlitArguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $streamlitScript + '" -ProjectRoot "' + $ProjectRoot + '" -PythonExe "' + $PythonExe + '"'

$mt5Action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $mt5Arguments
$controllerAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $controllerArguments
$streamlitAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $streamlitArguments
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

Register-ScheduledTask -TaskName "$TaskPrefix-MT5" -Action $mt5Action -Trigger $trigger -Principal $principalTask -Settings $settings -Description 'Supervisiona o MetaTrader 5 usado pelo Controlador Trading.' -Force | Out-Null
Register-ScheduledTask -TaskName "$TaskPrefix-Controlador" -Action $controllerAction -Trigger $trigger -Principal $principalTask -Settings $settings -Description 'Supervisiona o Controlador Trading e aguarda o MT5 DEMO.' -Force | Out-Null
Register-ScheduledTask -TaskName "$TaskPrefix-Streamlit" -Action $streamlitAction -Trigger $trigger -Principal $principalTask -Settings $settings -Description 'Supervisiona o painel web Streamlit em loopback.' -Force | Out-Null

if ($AutostartMode -eq 'AtStartupS4U') {
    Write-Host 'Inicialização 24/7 configurada para iniciar no boot sem depender de logon interativo (S4U).'
    Write-Host 'A compatibilidade do MT5 com esta sessão não-interativa ainda deve ser validada no host de produção antes de operar.'
} else {
    Write-Host 'Inicialização automática instalada para a sessão Windows atual (modo interativo).'
    Write-Host 'Este modo NÃO garante operação após logoff/reboot sem novo logon; use -AutostartMode AtStartupS4U no host 24/7 após validar o MT5.'
}
Write-Host 'MT5, Controlador e Streamlit serão supervisionados; o painel web permanece em 127.0.0.1:8501.'
Write-Host 'Configure o Tunnel para o hostname do painel apontar à porta 8501; mantenha a API 8000 privada.'
Write-Host 'A inicialização não altera nem compila o EA MQL5. Atualizações do EA exigem execução explícita e separada do utilitário de manutenção.'
Write-Host 'Nenhuma senha, token ou credencial foi gravada por este instalador.'
