param([Parameter(Mandatory=$true)][string]$BackupFile,[string]$PythonExe='python',[string]$RuntimeDir='',[string]$ProjectRoot='C:\Controlador-trade')
$ErrorActionPreference='Stop'
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
if(-not [System.IO.Path]::IsPathRooted($BackupFile)){$BackupFile=Join-Path $ProjectRoot $BackupFile}
$BackupFile=[System.IO.Path]::GetFullPath($BackupFile)
if(-not (Test-Path -LiteralPath $BackupFile -PathType Leaf)){throw "Backup não encontrado: $BackupFile"}
if($PythonExe -eq 'python' -or $PythonExe -eq 'python.exe'){$resolvedPython=Get-Command $PythonExe -ErrorAction SilentlyContinue;if($null -eq $resolvedPython -or [string]::IsNullOrWhiteSpace($resolvedPython.Source)){throw "Python não foi encontrado no PATH. Informe -PythonExe com o caminho completo do python.exe."};$PythonExe=$resolvedPython.Source}elseif(-not [System.IO.Path]::IsPathRooted($PythonExe)){$projectPython=Join-Path $ProjectRoot $PythonExe;if(Test-Path -LiteralPath $projectPython -PathType Leaf){$PythonExe=$projectPython}}
if(-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)){throw "Python não encontrado: $PythonExe"}
if([string]::IsNullOrWhiteSpace($RuntimeDir)){$RuntimeDir=Join-Path $ProjectRoot '.runtime'}elseif(-not [System.IO.Path]::IsPathRooted($RuntimeDir)){$RuntimeDir=Join-Path $ProjectRoot $RuntimeDir}
$RuntimeDir=[System.IO.Path]::GetFullPath($RuntimeDir)
Set-Location $ProjectRoot
$env:CONTROLADOR_RESTORE_BACKUP_FILE = $BackupFile
$env:CONTROLADOR_RESTORE_RUNTIME_DIR = $RuntimeDir
try {
    & $PythonExe -c "import os; from core.runtime_portability import restore_backup; print(restore_backup(os.environ['CONTROLADOR_RESTORE_BACKUP_FILE'], os.environ['CONTROLADOR_RESTORE_RUNTIME_DIR']))"
    $restoreExitCode = $LASTEXITCODE
} finally {
    Remove-Item Env:CONTROLADOR_RESTORE_BACKUP_FILE -ErrorAction SilentlyContinue
    Remove-Item Env:CONTROLADOR_RESTORE_RUNTIME_DIR -ErrorAction SilentlyContinue
}
if($restoreExitCode -ne 0){throw 'Falha ao restaurar o runtime.'}
