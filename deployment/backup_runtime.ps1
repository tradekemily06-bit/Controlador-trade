param([string]$ProjectRoot='C:\Controlador-trade',[string]$PythonExe='python',[string]$RuntimeDir='',[string]$OutputDir='')
$ErrorActionPreference='Stop'
if($PythonExe -eq 'python' -or $PythonExe -eq 'python.exe'){$resolvedPython=Get-Command $PythonExe -ErrorAction SilentlyContinue;if($null -eq $resolvedPython -or [string]::IsNullOrWhiteSpace($resolvedPython.Source)){throw "Python não foi encontrado no PATH. Informe -PythonExe com o caminho completo do python.exe."};$PythonExe=$resolvedPython.Source}
if(-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)){throw "Python não encontrado: $PythonExe"}
if([string]::IsNullOrWhiteSpace($RuntimeDir)){$RuntimeDir=Join-Path $ProjectRoot '.runtime'}
if([string]::IsNullOrWhiteSpace($OutputDir)){$OutputDir=Join-Path $ProjectRoot '.runtime-backups'}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$timestamp=Get-Date -Format 'yyyyMMdd-HHmmss'; $backup=Join-Path $OutputDir "controlador-runtime-$timestamp.zip"
Set-Location $ProjectRoot
& $PythonExe -c "from core.runtime_portability import create_backup; print(create_backup(r'$RuntimeDir',r'$backup'))"
if($LASTEXITCODE -ne 0){throw 'Falha ao criar backup do runtime.'}
