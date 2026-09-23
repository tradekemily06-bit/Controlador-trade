$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$python = (Get-Command python -ErrorAction Stop).Source
$existing = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -like "*$Root*app.py*" }
if (-not $existing) { Start-Process -FilePath $python -ArgumentList @("$Root\app.py") -WorkingDirectory $Root -WindowStyle Hidden }
