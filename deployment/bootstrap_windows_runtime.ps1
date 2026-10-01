param(
    [string]$ProjectRoot = 'C:\Controlador-trade',
    [string]$PythonExe = 'python',
    [string]$RuntimeDir = 'C:\Controlador-trade\.runtime'
)

$ErrorActionPreference = 'Stop'

$currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Execute o bootstrap uma única vez em um PowerShell como Administrador.'
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

# Persist only non-secret runtime configuration at machine scope so the
# environment survives reboot. Secrets remain external and are never written
# to this repository or this script.
$machineSettings = @{
    CONTROLADOR_BIND_HOST = '127.0.0.1'
    PORT = '8000'
    CONTROLADOR_EXECUTION_PROVIDER = 'ic_markets_mt5_demo'
    CONTROLADOR_REMOTE_ACCESS_REQUIRED = 'true'
    CONTROLADOR_TRUSTED_IDENTITY_HEADER = 'Cf-Access-Authenticated-User-Email'
    CONTROLADOR_RUNTIME_DIR = $RuntimeDir
    CONTROLADOR_SECURITY_AUDIT_DB = (Join-Path $RuntimeDir 'security-audit.sqlite')
}

foreach ($entry in $machineSettings.GetEnumerator()) {
    [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Machine')
    Set-Item -Path ("Env:" + $entry.Key) -Value $entry.Value
}

Set-Location $ProjectRoot
& $PythonExe -m pip install -r requirements.txt
& $PythonExe -m pip install -r requirements-mt5.txt

Write-Host 'Verificando import do MetaTrader5...'
& $PythonExe -c 'import MetaTrader5; print(MetaTrader5.__version__)'

Write-Host 'Bootstrap concluido. O runtime sera iniciado somente em loopback.'
Write-Host 'A configuracao nao-secreta foi persistida para sobreviver a reinicios do Windows.'
Write-Host 'Configure o Cloudflare Tunnel/Access antes de liberar o hostname.'
Write-Host 'Nao coloque CONTROLADOR_UPDATE_TOKEN ou credenciais no arquivo.'
