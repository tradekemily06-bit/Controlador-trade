param(
    [string]$ProjectRoot = 'C:\Controlador-trade',
    [string]$PythonExe = 'python',
    [string]$RuntimeDir = 'C:\Controlador-trade\.runtime'
 )

$ErrorActionPreference = 'Stop'

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

$env:CONTROLADOR_BIND_HOST = '127.0.0.1'
$env:PORT = '8000'
$env:CONTROLADOR_EXECUTION_PROVIDER = 'ic_markets_mt5_demo'
$env:CONTROLADOR_REMOTE_ACCESS_REQUIRED = 'true'
$env:CONTROLADOR_TRUSTED_IDENTITY_HEADER = 'Cf-Access-Authenticated-User-Email'
$env:CONTROLADOR_RUNTIME_DIR = $RuntimeDir
$env:CONTROLADOR_SECURITY_AUDIT_DB = Join-Path $RuntimeDir 'security-audit.sqlite'

Set-Location $ProjectRoot
& $PythonExe -m pip install -r requirements.txt
& $PythonExe -m pip install -r requirements-mt5.txt

Write-Host 'Verificando import do MetaTrader5...'
& $PythonExe -c 'import MetaTrader5; print(MetaTrader5.__version__)'

Write-Host 'Bootstrap concluido. O runtime sera iniciado somente em loopback.'
Write-Host 'Configure o Cloudflare Tunnel/Access antes de liberar o hostname.'
Write-Host 'Nao coloque CONTROLADOR_UPDATE_TOKEN ou credenciais no arquivo.'