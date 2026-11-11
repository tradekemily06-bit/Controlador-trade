param([string]$ProjectRoot='C:\Controlador-trade',[string]$PythonExe='python',[string]$RuntimeDir='',[string]$OutputDir='')
$ErrorActionPreference='Stop'
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
if($PythonExe -eq 'python' -or $PythonExe -eq 'python.exe'){$resolvedPython=Get-Command $PythonExe -ErrorAction SilentlyContinue;if($null -eq $resolvedPython -or [string]::IsNullOrWhiteSpace($resolvedPython.Source)){throw "Python não foi encontrado no PATH. Informe -PythonExe com o caminho completo do python.exe."};$PythonExe=$resolvedPython.Source}
if(-not [System.IO.Path]::IsPathRooted($PythonExe)){$projectPython=Join-Path $ProjectRoot $PythonExe;if(Test-Path -LiteralPath $projectPython -PathType Leaf){$PythonExe=$projectPython}else{$PythonExe=[System.IO.Path]::GetFullPath($PythonExe)}}
$PythonExe=[System.IO.Path]::GetFullPath($PythonExe)
if(-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)){throw "Python não encontrado: $PythonExe"}
if([string]::IsNullOrWhiteSpace($RuntimeDir)){$RuntimeDir=Join-Path $ProjectRoot '.runtime'}elseif(-not [System.IO.Path]::IsPathRooted($RuntimeDir)){$RuntimeDir=Join-Path $ProjectRoot $RuntimeDir}
$RuntimeDir=[System.IO.Path]::GetFullPath($RuntimeDir)
if([string]::IsNullOrWhiteSpace($OutputDir)){$OutputDir=Join-Path $ProjectRoot '.runtime-backups'}elseif(-not [System.IO.Path]::IsPathRooted($OutputDir)){$OutputDir=Join-Path $ProjectRoot $OutputDir}
$OutputDir=[System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$timestamp=Get-Date -Format 'yyyyMMdd-HHmmss-fff'; $backup=Join-Path $OutputDir ("controlador-runtime-$timestamp-$([guid]::NewGuid().ToString('N')).zip")
Set-Location $ProjectRoot
$env:CONTROLADOR_BACKUP_RUNTIME_DIR = $RuntimeDir
$env:CONTROLADOR_BACKUP_OUTPUT_FILE = $backup
try {
    & $PythonExe -c "import os; from core.runtime_portability import create_backup; print(create_backup(os.environ['CONTROLADOR_BACKUP_RUNTIME_DIR'], os.environ['CONTROLADOR_BACKUP_OUTPUT_FILE']))"
    $backupExitCode = $LASTEXITCODE
} finally {
    Remove-Item Env:CONTROLADOR_BACKUP_RUNTIME_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:CONTROLADOR_BACKUP_OUTPUT_FILE -ErrorAction SilentlyContinue
}
if($backupExitCode -ne 0){throw 'Falha ao criar backup do runtime.'}
