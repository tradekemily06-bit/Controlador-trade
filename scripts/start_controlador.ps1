$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$python = (Get-Command py -ErrorAction SilentlyContinue).Source
if (-not $python) {
    $python = (Get-Command python -ErrorAction Stop).Source
}
$resolvedPython = [System.IO.Path]::GetFullPath($python)
$trustedRoots = @(
    [System.IO.Path]::GetFullPath("$env:WINDIR"),
    [System.IO.Path]::GetFullPath("$env:ProgramFiles\Python"),
    [System.IO.Path]::GetFullPath("$env:LOCALAPPDATA\Programs\Python")
)
if (-not ($trustedRoots | Where-Object { $resolvedPython.StartsWith($_, [System.StringComparison]::OrdinalIgnoreCase) })) {
    throw "Refusing to launch Python from an unexpected location: $resolvedPython"
}

$existing = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -like "*$Root*app.py*" }
if (-not $existing) {
    Start-Process -FilePath $python -ArgumentList @("-c", "import sys; sys.path.insert(0, r'$Root'); from app import run; run(host='127.0.0.1')") -WorkingDirectory $Root -WindowStyle Hidden
}
Start-Sleep -Seconds 2
try { Start-Process "http://127.0.0.1:8000" } catch {}
