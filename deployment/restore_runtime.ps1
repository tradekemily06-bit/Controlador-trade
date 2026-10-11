param([Parameter(Mandatory=$true)][string]$BackupFile,[string]$PythonExe='python',[string]$RuntimeDir='',[string]$ProjectRoot='C:\Controlador-trade',[switch]$Replace)
$ErrorActionPreference='Stop'
if($PythonExe -eq 'python' -or $PythonExe -eq 'python.exe'){$resolvedPython=Get-Command $PythonExe -ErrorAction SilentlyContinue;if($null -eq $resolvedPython -or [string]::IsNullOrWhiteSpace($resolvedPython.Source)){throw "Python não foi encontrado no PATH. Informe -PythonExe com o caminho completo do python.exe."};$PythonExe=$resolvedPython.Source}
if(-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)){throw "Python não encontrado: $PythonExe"}
if([string]::IsNullOrWhiteSpace($RuntimeDir)){$RuntimeDir=Join-Path $ProjectRoot '.runtime'}
Set-Location $ProjectRoot
$replaceFlag = if ($Replace) { 'true' } else { 'false' }
& $PythonExe -c "import sys; from core.runtime_portability import restore_backup; print(restore_backup(sys.argv[1], sys.argv[2], replace=(sys.argv[3] == 'true')))" $BackupFile $RuntimeDir $replaceFlag
if($LASTEXITCODE -ne 0){throw 'Falha ao restaurar o runtime.'}
