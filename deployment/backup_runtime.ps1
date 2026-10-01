param([string]$ProjectRoot='C:\Controlador-trade',[string]$RuntimeDir='C:\Controlador-trade\.runtime',[string]$OutputDir='C:\Controlador-trade\.runtime-backups')
$ErrorActionPreference='Stop'; New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$timestamp=Get-Date -Format 'yyyyMMdd-HHmmss'; $backup=Join-Path $OutputDir "controlador-runtime-$timestamp.zip"
Set-Location $ProjectRoot
& python -c "from core.runtime_portability import create_backup; print(create_backup(r'$RuntimeDir',r'$backup'))"
if($LASTEXITCODE -ne 0){throw 'Falha ao criar backup do runtime.'}
