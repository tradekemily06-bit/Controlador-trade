param(
    [string]$ProjectRoot = 'C:\Controlador-trade',
    [string]$PythonExe = 'python',
    [int]$RestartDelaySeconds = 10,
    [int]$MaxRestartsPerHour = 6
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)

if ($PythonExe -eq 'python' -or $PythonExe -eq 'python.exe') {
    $resolvedPython = Get-Command $PythonExe -ErrorAction SilentlyContinue
    if ($null -eq $resolvedPython -or [string]::IsNullOrWhiteSpace($resolvedPython.Source)) {
        throw "Python não foi encontrado no PATH. Informe -PythonExe com o caminho completo do python.exe."
    }
    $PythonExe = $resolvedPython.Source
} elseif (-not [System.IO.Path]::IsPathRooted($PythonExe)) {
    $projectPython = Join-Path $ProjectRoot $PythonExe
    if (Test-Path -LiteralPath $projectPython -PathType Leaf) {
        $PythonExe = [System.IO.Path]::GetFullPath($projectPython)
    }
}
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Python não encontrado: $PythonExe"
}

$panelScript = Join-Path $ProjectRoot 'streamlit_panel\app.py'
$panelRequirements = Join-Path $ProjectRoot 'streamlit_panel\requirements.txt'
if (-not (Test-Path -LiteralPath $panelScript -PathType Leaf)) {
    throw "Aplicação Streamlit não encontrada: $panelScript"
}
if (-not (Test-Path -LiteralPath $panelRequirements -PathType Leaf)) {
    throw "Dependências do Streamlit não encontradas: $panelRequirements"
}

# Keep the web panel private on loopback. Cloudflare Access/Tunnel is the only
# supported remote entry point; the API remains a separate private service.
$env:CONTROLADOR_API_BASE_URL = 'http://127.0.0.1:8000'
$env:CONTROLADOR_REMOTE_ACCESS_REQUIRED = 'true'
$env:CONTROLADOR_TRUSTED_IDENTITY_HEADER = 'Cf-Access-Authenticated-User-Email'
$env:STREAMLIT_SERVER_ADDRESS = '127.0.0.1'
$env:STREAMLIT_SERVER_PORT = '8501'
$env:STREAMLIT_SERVER_HEADLESS = 'true'
$env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = 'false'

$runtimeDir = Join-Path $ProjectRoot '.runtime'
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
$stdoutPath = Join-Path $runtimeDir 'streamlit-panel.stdout.log'
$stderrPath = Join-Path $runtimeDir 'streamlit-panel.stderr.log'
$statusPath = Join-Path $runtimeDir 'streamlit-panel-supervisor-status.json'
$restartTimes = New-Object System.Collections.Generic.List[datetime]

function Write-PanelStatus([string]$State, [string]$Reason) {
    $payload = @{
        component = 'streamlit-panel'
        state = $State
        reason = $Reason
        bind_host = '127.0.0.1'
        port = 8501
        api_base_url = 'http://127.0.0.1:8000'
        observed_at = (Get-Date).ToUniversalTime().ToString('o')
        restart_count_last_hour = $restartTimes.Count
    } | ConvertTo-Json -Compress
    $tmp = "$statusPath.tmp"
    Set-Content -LiteralPath $tmp -Value $payload -Encoding UTF8
    Move-Item -LiteralPath $tmp -Destination $statusPath -Force
}

$finalState = 'STOPPED'
$finalReason = 'Supervisor finalizado.'
try {
    while ($true) {
        $cutoff = (Get-Date).AddHours(-1)
        for ($i = $restartTimes.Count - 1; $i -ge 0; $i--) {
            if ($restartTimes[$i] -lt $cutoff) { $restartTimes.RemoveAt($i) }
        }
        if ($restartTimes.Count -ge $MaxRestartsPerHour) {
            $finalState = 'ATTENTION'
            $finalReason = "Orçamento de reinícios excedido: $MaxRestartsPerHour por hora."
            Write-PanelStatus $finalState $finalReason
            break
        }

        Write-PanelStatus 'STARTING' 'Iniciando Streamlit somente em 127.0.0.1:8501.'
        $arguments = '-m streamlit run "' + $panelScript + '" --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false'
        $process = Start-Process -FilePath $PythonExe -ArgumentList $arguments -WorkingDirectory $ProjectRoot -PassThru -Wait -NoNewWindow -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
        $exitCode = $process.ExitCode
        $restartTimes.Add((Get-Date))
        $finalReason = "Streamlit encerrou com código $exitCode."
        Write-PanelStatus 'RESTARTING' $finalReason
        Start-Sleep -Seconds $RestartDelaySeconds
    }
} catch {
    $finalState = 'ATTENTION'
    $finalReason = $_.Exception.Message
    Write-PanelStatus $finalState $finalReason
    throw
} finally {
    if ($finalState -eq 'STOPPED') {
        Write-PanelStatus $finalState $finalReason
    }
}
