param([Parameter(Mandatory=$true)][string]$BackupFile,[string]$PythonExe='python',[string]$RuntimeDir='',[string]$ProjectRoot='C:\Controlador-trade')
$ErrorActionPreference='Stop'
if($PythonExe -eq 'python' -or $PythonExe -eq 'python.exe'){$resolvedPython=Get-Command $PythonExe -ErrorAction SilentlyContinue;if($null -eq $resolvedPython -or [string]::IsNullOrWhiteSpace($resolvedPython.Source)){throw "Python não foi encontrado no PATH. Informe -PythonExe com o caminho completo do python.exe."};$PythonExe=$resolvedPython.Source}
if(-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)){throw "Python não encontrado: $PythonExe"}
if([string]::IsNullOrWhiteSpace($RuntimeDir)){$RuntimeDir=Join-Path $ProjectRoot '.runtime'}
Set-Location $ProjectRoot
$env:CONTROLADOR_RESTORE_BACKUP_FILE = $BackupFile
$env:CONTROLADOR_RESTORE_RUNTIME_DIR = $RuntimeDir
try {
    & $PythonExe -c 'import os; from core.runtime_portability import restore_backup; print(restore_backup(os.environ["CONTROLADOR_RESTORE_BACKUP_FILE"], os.environ["CONTROLADOR_RESTORE_RUNTIME_DIR"]))'
    $restoreExitCode = $LASTEXITCODE
} finally {
    Remove-Item Env:CONTROLADOR_RESTORE_BACKUP_FILE -ErrorAction SilentlyContinue
    Remove-Item Env:CONTROLADOR_RESTORE_RUNTIME_DIR -ErrorAction SilentlyContinue
}
if($restoreExitCode -ne 0){throw 'Falha ao restaurar o runtime.'}
