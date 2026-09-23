$ErrorActionPreference = "SilentlyContinue"
$Root = Split-Path -Parent $PSScriptRoot
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -like "*$Root*app.py*" -or $_.CommandLine -like "*from app import run*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Write-Host "Controlador Trading encerrado." -ForegroundColor Yellow
