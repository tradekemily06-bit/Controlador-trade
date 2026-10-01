param([Parameter(Mandatory=$true)][string]$BackupFile,[string]$PythonExe='python',[string]$RuntimeDir='C:\Controlador-trade\.runtime',[string]$ProjectRoot='C:\Controlador-trade')
$ErrorActionPreference='Stop'; Set-Location $ProjectRoot
& $PythonExe -c "from core.runtime_portability import restore_backup; print(restore_backup(r'$BackupFile',r'$RuntimeDir'))"
if($LASTEXITCODE -ne 0){throw 'Falha ao restaurar o runtime.'}
