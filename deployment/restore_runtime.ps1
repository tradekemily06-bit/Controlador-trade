param([Parameter(Mandatory=$true)][string]$BackupFile,[string]$RuntimeDir='C:\Controlador-trade\.runtime',[string]$ProjectRoot='C:\Controlador-trade')
$ErrorActionPreference='Stop'; Set-Location $ProjectRoot
& python -c "from core.runtime_portability import restore_backup; print(restore_backup(r'$BackupFile',r'$RuntimeDir'))"
if($LASTEXITCODE -ne 0){throw 'Falha ao restaurar o runtime.'}
