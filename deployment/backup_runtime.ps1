param([string]$ProjectRoot='C:\Controlador-trade',[string]$PythonExe='python',[string]$RuntimeDir='',[string]$OutputDir='')
$ErrorActionPreference='Stop'
if([string]::IsNullOrWhiteSpace($RuntimeDir)){$RuntimeDir=Join-Path $ProjectRoot '.runtime'}
if([string]::IsNullOrWhiteSpace($OutputDir)){$OutputDir=Join-Path $ProjectRoot '.runtime-backups'}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$timestamp=Get-Date -Format 'yyyyMMdd-HHmmss'; $backup=Join-Path $OutputDir "controlador-runtime-$timestamp.zip"
Set-Location $ProjectRoot
& $PythonExe -c "from core.runtime_portability import create_backup; print(create_backup(r'$RuntimeDir',r'$backup'))"
if($LASTEXITCODE -ne 0){throw 'Falha ao criar backup do runtime.'}
