[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonExe = 'python',
    [string]$MetaEditorPath = '',
    [string]$Mt5TerminalPath = '',
    [string]$Mt5DataPath = $env:CONTROLADOR_MT5_DATA_PATH,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

function Copy-WithRetry([string]$Source, [string]$Destination, [int]$Attempts = 5) {
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            Copy-Item -LiteralPath $Source -Destination $Destination -Force -ErrorAction Stop
            return
        } catch {
            if ($attempt -eq $Attempts) { throw }
            Start-Sleep -Milliseconds (250 * $attempt)
        }
    }
}

$script:RestoreFailures = [System.Collections.Generic.List[string]]::new()

function Restore-File([string]$Backup, [string]$Target) {
    try {
        if (Test-Path -LiteralPath $Backup -PathType Leaf) {
            Copy-WithRetry -Source $Backup -Destination $Target
            if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) {
                throw 'O arquivo restaurado não existe no destino.'
            }
            $backupHash = (Get-FileHash -LiteralPath $Backup -Algorithm SHA256).Hash
            $targetHash = (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash
            if ($backupHash -ne $targetHash) {
                throw 'O hash do arquivo restaurado diverge do backup.'
            }
        } elseif (Test-Path -LiteralPath $Target -PathType Leaf) {
            Remove-Item -LiteralPath $Target -Force -ErrorAction Stop
            if (Test-Path -LiteralPath $Target -PathType Leaf) {
                throw 'O arquivo novo não foi removido durante a restauração.'
            }
        }
        return $true
    } catch {
        [void]$script:RestoreFailures.Add("$Target :: $($_.Exception.Message)")
        Write-Error "Falha ao restaurar '$Target': $($_.Exception.Message)" -ErrorAction Continue
        return $false
    }
}

function Assert-RestoreComplete {
    if ($script:RestoreFailures.Count -gt 0) {
        $details = $script:RestoreFailures -join ' | '
        throw "ROLLBACK_INCOMPLETO: um ou mais artefatos não puderam ser restaurados. $details"
    }
}

function Resolve-Mt5TerminalPath([string]$RequestedPath) {
    # The Python MT5 bridge selects a terminal by executable path, not by PID/data folder.
    # If two running terminals share that executable path, fail closed rather than
    # copying/compiling the panel into an arbitrary instance's data directory.
    $processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ieq 'terminal64.exe' })
    if ($processes.Count -eq 0) {
        throw 'Nenhum processo terminal64.exe está em execução; não é possível confirmar o terminal de destino do painel.'
    }

    if ([string]::IsNullOrWhiteSpace($RequestedPath)) {
        $resolvedPaths = @($processes |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_.ExecutablePath) } |
            ForEach-Object { [System.IO.Path]::GetFullPath($_.ExecutablePath) } |
            Sort-Object -Unique)
        if ($resolvedPaths.Count -gt 1) {
            throw 'Mais de uma instalação do MT5 está em execução; informe -Mt5TerminalPath explicitamente.'
        }
        if ($resolvedPaths.Count -eq 0) {
            throw 'Não foi possível resolver o caminho executável do MT5 em execução.'
        }
        return $resolvedPaths[0]
    }

    $requested = [System.IO.Path]::GetFullPath($RequestedPath)
    $matching = @($processes | Where-Object {
        if (-not [string]::IsNullOrWhiteSpace($_.ExecutablePath)) {
            [string]::Equals(
                [System.IO.Path]::GetFullPath($_.ExecutablePath),
                $requested,
                [System.StringComparison]::OrdinalIgnoreCase
            )
        } elseif (-not [string]::IsNullOrWhiteSpace($_.CommandLine)) {
            $_.CommandLine.IndexOf($requested, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
        } else {
            $false
        }
    })

    if ($matching.Count -eq 0) {
        throw "Nenhum processo em execução corresponde ao MT5 configurado: $requested"
    }
    # Multiple processes may share the executable but use different data folders.
    # Resolve the data folder independently before deciding where to deploy the EA.
    return $requested
}

$Mt5TerminalPath = Resolve-Mt5TerminalPath -RequestedPath $Mt5TerminalPath

$source = Join-Path $ProjectRoot 'mql5\Experts\ControladorTrading\Controlador-Trading.mq5'
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Fonte MQL5 não encontrada: $source"
}

function Get-Mt5Paths {
    param([string]$TerminalPath)
    $code = @'
import json
import os
import sys
import MetaTrader5 as mt5
requested = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else ""
if not mt5.initialize(path=requested or None):
    raise SystemExit("MT5_INIT_FAILED:" + str(mt5.last_error()))
info = mt5.terminal_info()
if info is None:
    mt5.shutdown()
    raise SystemExit("MT5_TERMINAL_INFO_FAILED")
if requested:
    expected = os.path.normcase(os.path.realpath(requested))
    actual = os.path.normcase(os.path.realpath(os.path.join(getattr(info, "path", ""), os.path.basename(requested))))
    if actual != expected:
        mt5.shutdown()
        raise SystemExit("MT5_CONFIGURED_PATH_MISMATCH")
print(json.dumps({
    "path": getattr(info, "path", ""),
    "data_path": getattr(info, "data_path", "")
}))
mt5.shutdown()
'@
    # Base64 keeps multiline Python intact across PowerShell/native argument parsing.
    $encodedCode = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($code))
    $oneLineCode = "import base64;exec(compile(base64.b64decode('$encodedCode'),'<mt5-paths>','exec'))"
    $result = & $PythonExe -c $oneLineCode $TerminalPath 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $result) { return $null }
    try { return ($result | ConvertFrom-Json) } catch { return $null }
}

function Resolve-Mt5DataPath([string]$RequestedPath, [string]$TerminalPath) {
    if (-not [string]::IsNullOrWhiteSpace($RequestedPath)) {
        $resolved = [System.IO.Path]::GetFullPath($RequestedPath)
        if (-not (Test-Path -LiteralPath $resolved -PathType Container)) {
            throw "Pasta de dados MT5 configurada não encontrada: $resolved"
        }
        if (-not (Test-Path -LiteralPath (Join-Path $resolved 'MQL5') -PathType Container)) {
            throw "Pasta configurada não parece ser uma pasta de dados MT5 (MQL5 ausente): $resolved"
        }
        return $resolved
    }

    # Prefer the unique existing terminal data folder that already owns this EA.
    # This allows multiple terminal64.exe processes without guessing which data
    # directory is intended. If more than one candidate exists, fail closed.
    $profilesRoot = Join-Path $env:APPDATA 'MetaQuotes\Terminal'
    $candidates = @()
    if (Test-Path -LiteralPath $profilesRoot -PathType Container) {
        foreach ($profile in @(Get-ChildItem -LiteralPath $profilesRoot -Directory -ErrorAction SilentlyContinue)) {
            $eaDir = Join-Path $profile.FullName 'MQL5\Experts\ControladorTrading'
            $sourcePresent = Test-Path -LiteralPath (Join-Path $eaDir 'Controlador-Trading.mq5') -PathType Leaf
            $binaryPresent = Test-Path -LiteralPath (Join-Path $eaDir 'Controlador-Trading.ex5') -PathType Leaf
            if ($sourcePresent -or $binaryPresent) {
                $candidates += $profile.FullName
            }
        }
    }
    $candidates = @($candidates | Sort-Object -Unique)
    if ($candidates.Count -eq 1) { return [System.IO.Path]::GetFullPath($candidates[0]) }
    if ($candidates.Count -gt 1) {
        throw "Mais de uma pasta de dados MT5 contém o painel; configure CONTROLADOR_MT5_DATA_PATH explicitamente: $($candidates -join '; ')"
    }

    # A fresh install may not yet have an EA file to identify its data directory.
    # In that case the Python bridge fallback is allowed only when one process
    # matches the configured terminal executable.
    $matchingProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -ieq ([System.IO.Path]::GetFileName($TerminalPath)) -and
            -not [string]::IsNullOrWhiteSpace($_.ExecutablePath) -and
            [string]::Equals(
                [System.IO.Path]::GetFullPath($_.ExecutablePath),
                [System.IO.Path]::GetFullPath($TerminalPath),
                [System.StringComparison]::OrdinalIgnoreCase
            )
        })
    if ($matchingProcesses.Count -gt 1) {
        throw 'Várias instâncias do MT5 estão ativas e nenhuma pasta de dados contém o painel; configure CONTROLADOR_MT5_DATA_PATH para evitar um destino ambíguo.'
    }
    if ($WhatIfPreference) {
        throw 'Simulação -WhatIf não inicializa o terminal MT5. Informe -Mt5DataPath ou CONTROLADOR_MT5_DATA_PATH, ou mantenha uma única pasta de dados existente que contenha o EA.'
    }

    $paths = Get-Mt5Paths -TerminalPath $TerminalPath
    if (-not $paths -or [string]::IsNullOrWhiteSpace($paths.data_path)) {
        throw 'Não foi possível resolver a pasta de dados MT5 com segurança.'
    }
    $resolvedDataPath = [System.IO.Path]::GetFullPath([string]$paths.data_path)
    if (-not (Test-Path -LiteralPath $resolvedDataPath -PathType Container) -or
        -not (Test-Path -LiteralPath (Join-Path $resolvedDataPath 'MQL5') -PathType Container)) {
        throw "A ponte MT5 retornou uma pasta de dados inválida: $resolvedDataPath"
    }
    return $resolvedDataPath
}

$dataPath = Resolve-Mt5DataPath -RequestedPath $Mt5DataPath -TerminalPath $Mt5TerminalPath
$terminalInstallPath = Split-Path -Parent $Mt5TerminalPath
$destinationDir = Join-Path $dataPath 'MQL5\Experts\ControladorTrading'
$destination = Join-Path $destinationDir 'Controlador-Trading.mq5'

if ([string]::IsNullOrWhiteSpace($MetaEditorPath)) {
    $candidate = Join-Path $terminalInstallPath 'metaeditor64.exe'
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $MetaEditorPath = $candidate
    } else {
        $candidate = Join-Path $terminalInstallPath 'metaeditor.exe'
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { $MetaEditorPath = $candidate }
    }
}
if (-not (Test-Path -LiteralPath $MetaEditorPath -PathType Leaf)) {
    throw 'MetaEditor não encontrado ao lado do terminal conectado.'
}

$sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
$destinationHash = if (Test-Path -LiteralPath $destination -PathType Leaf) { (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash } else { '' }
$binary = [System.IO.Path]::ChangeExtension($destination, '.ex5')
$provenance = "$binary.provenance.json"
$log = [System.IO.Path]::ChangeExtension($destination, '.log')
$sourceWriteTime = (Get-Item -LiteralPath $source).LastWriteTime
$binaryUsable = $false
if ((Test-Path -LiteralPath $binary -PathType Leaf) -and (Test-Path -LiteralPath $provenance -PathType Leaf)) {
    try {
        $recordedProvenance = Get-Content -LiteralPath $provenance -Raw | ConvertFrom-Json
        $currentBinaryHash = (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash
        $binaryWriteTime = (Get-Item -LiteralPath $binary).LastWriteTime
        $binaryUsable = (
            [string]$recordedProvenance.source_sha256 -eq $sourceHash -and
            [string]$recordedProvenance.binary_sha256 -eq $currentBinaryHash -and
            $binaryWriteTime -ge $sourceWriteTime
        )
    } catch {
        $binaryUsable = $false
    }
}

if (-not $Force -and $sourceHash -eq $destinationHash -and $binaryUsable) {
    Write-Host "MQL5 + EX5 já sincronizados; proveniência da compilação confirmada: $destination"
    exit 0
}

if (-not $Force -and $sourceHash -eq $destinationHash -and -not $binaryUsable) {
    Write-Host "Fonte já sincronizada, mas EX5 ausente/desatualizado; recompilando."
}

$actionDescription = "Substituir o fonte .mq5 e o binário .ex5, atualizar a proveniência e recriar/remover o log de compilação no terminal MT5 selecionado"
if (-not $PSCmdlet.ShouldProcess($destination, $actionDescription)) {
    Write-Host 'Sincronização/compilação não executada; nenhum arquivo do EA foi alterado.'
    return
}

$stamp = (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N')
$backupSource = "$destination.$stamp.bak"
$backupBinary = [System.IO.Path]::ChangeExtension($destination, '.ex5') + ".$stamp.bak"
$backupProvenance = "$provenance.$stamp.bak"
$backupLog = "$log.$stamp.bak"
$backupTargets = @($backupSource, $backupBinary, $backupProvenance, $backupLog)
$backupCollision = @($backupTargets | Where-Object { Test-Path -LiteralPath $_ })
if ($backupCollision.Count -gt 0) {
    throw "Backup com nome já existente; nenhum artefato do EA foi alterado. Escolha uma nova execução após inspecionar: $($backupCollision -join '; ')"
}
New-Item -ItemType Directory -Force -Path $destinationDir | Out-Null
try {
    if (Test-Path -LiteralPath $destination) { Copy-WithRetry -Source $destination -Destination $backupSource }
    if (Test-Path -LiteralPath $binary) { Copy-WithRetry -Source $binary -Destination $backupBinary }
    if (Test-Path -LiteralPath $provenance) { Copy-WithRetry -Source $provenance -Destination $backupProvenance }
    if (Test-Path -LiteralPath $log) { Copy-WithRetry -Source $log -Destination $backupLog }
} catch {
    throw "Falha ao criar os backups dos artefatos; o destino do EA ainda não foi modificado. Backups parciais foram preservados para inspeção. $($_.Exception.Message)"
}

try {
    Copy-WithRetry -Source $source -Destination $destination
    $copiedSourceHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
    if ($copiedSourceHash -ne $sourceHash) {
        throw "A fonte mudou durante a sincronização; destino será restaurado: $destination"
    }
} catch {
    $script:RestoreFailures.Clear()
    Restore-File -Backup $backupSource -Target $destination
    Restore-File -Backup $backupBinary -Target $binary
    Restore-File -Backup $backupProvenance -Target $provenance
    Restore-File -Backup $backupLog -Target $log
    Assert-RestoreComplete
    throw "Falha ao substituir a fonte MQL5; arquivos anteriores restaurados. $($_.Exception.Message)"
}

$provenanceTemp = "$provenance.$stamp.tmp"
try {
    if (Test-Path -LiteralPath $log) { Remove-Item -LiteralPath $log -Force }
    $compileStartedAt = Get-Date
$explicitLog = $log
$binaryHashBefore = if (Test-Path -LiteralPath $binary -PathType Leaf) { (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash } else { '' }

& $MetaEditorPath "/compile:$destination" "/log:$explicitLog" | Out-Null
$metaEditorExitCode = $LASTEXITCODE
Start-Sleep -Milliseconds 500
if (-not (Test-Path -LiteralPath $log -PathType Leaf)) {
    $script:RestoreFailures.Clear()
    Restore-File -Backup $backupSource -Target $destination
    Restore-File -Backup $backupBinary -Target $binary
    Restore-File -Backup $backupProvenance -Target $provenance
    Restore-File -Backup $backupLog -Target $log
    Assert-RestoreComplete
    throw "MetaEditor não produziu log de compilação: $log"
}

$logText = Get-Content -LiteralPath $log -Raw -ErrorAction SilentlyContinue
$errorMatch = [regex]::Match($logText, '(?i)(\d+)\s+(errors?|erros?)')
$warningMatch = [regex]::Match($logText, '(?i)(\d+)\s+(warnings?|avisos?)')
if (-not $errorMatch.Success -or -not $warningMatch.Success) {
    $script:RestoreFailures.Clear()
    Restore-File -Backup $backupSource -Target $destination
    Restore-File -Backup $backupBinary -Target $binary
    Restore-File -Backup $backupProvenance -Target $provenance
    Restore-File -Backup $backupLog -Target $log
    Assert-RestoreComplete
    throw "Log de compilação sem contagem inequívoca de erros/avisos: $log"
}
$errors = $errorMatch.Groups[1].Value
$warnings = $warningMatch.Groups[1].Value
if ($errors -ne '0' -or $warnings -ne '0') {
    $script:RestoreFailures.Clear()
    Restore-File -Backup $backupSource -Target $destination
    Restore-File -Backup $backupBinary -Target $binary
    Restore-File -Backup $backupProvenance -Target $provenance
    Restore-File -Backup $backupLog -Target $log
    Assert-RestoreComplete
    throw "Compilação MQL5 rejeitada: errors=$errors warnings=$warnings. Log: $log"
}

if (-not (Test-Path -LiteralPath $binary -PathType Leaf)) {
    $script:RestoreFailures.Clear()
    Restore-File -Backup $backupSource -Target $destination
    Restore-File -Backup $backupBinary -Target $binary
    Restore-File -Backup $backupProvenance -Target $provenance
    Restore-File -Backup $backupLog -Target $log
    Assert-RestoreComplete
    throw "MetaEditor terminou sem gerar o EX5 esperado: $binary"
}

$binaryWriteTime = (Get-Item -LiteralPath $binary).LastWriteTime
$binaryHashAfter = (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash
if ($binaryWriteTime -lt $compileStartedAt.AddSeconds(-2)) {
    $script:RestoreFailures.Clear()
    Restore-File -Backup $backupSource -Target $destination
    Restore-File -Backup $backupBinary -Target $binary
    Restore-File -Backup $backupProvenance -Target $provenance
    Restore-File -Backup $backupLog -Target $log
    Assert-RestoreComplete
    throw "O EX5 não foi atualizado pela compilação (timestamp anterior à compilação): $binary"
}

    $provenancePayload = @{
    schema_version = 1
    source_sha256 = $sourceHash
    binary_sha256 = $binaryHashAfter
    compiled_at_utc = (Get-Date).ToUniversalTime().ToString('o')
}
try {
    ($provenancePayload | ConvertTo-Json -Compress) |
        Set-Content -LiteralPath $provenanceTemp -Encoding ASCII
    Move-Item -LiteralPath $provenanceTemp -Destination $provenance -Force
} catch {
    $script:RestoreFailures.Clear()
    Restore-File -Backup $backupSource -Target $destination
    Restore-File -Backup $backupBinary -Target $binary
    Restore-File -Backup $backupProvenance -Target $provenance
    Restore-File -Backup $backupLog -Target $log
    Assert-RestoreComplete
    Remove-Item -LiteralPath $provenanceTemp -Force -ErrorAction SilentlyContinue
    throw "Não foi possível registrar a proveniência da compilação; arquivos anteriores restaurados. $($_.Exception.Message)"
}


} catch {
    $script:RestoreFailures.Clear()
    Restore-File -Backup $backupSource -Target $destination
    Restore-File -Backup $backupBinary -Target $binary
    Restore-File -Backup $backupProvenance -Target $provenance
    Restore-File -Backup $backupLog -Target $log
    Assert-RestoreComplete
    Remove-Item -LiteralPath $provenanceTemp -Force -ErrorAction SilentlyContinue
    throw "Falha inesperada na sincronização/compilação; artefatos anteriores restaurados. $($_.Exception.Message)"
}

if ($metaEditorExitCode -ne 0) {
    Write-Warning "MetaEditor retornou código $metaEditorExitCode, mas o log confirmou 0 erros/avisos e o EX5 foi atualizado. Resultado validado pelos artefatos."
}

Remove-Item -LiteralPath $log -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $backupSource -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $backupBinary -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $backupProvenance -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $backupLog -Force -ErrorAction SilentlyContinue

Write-Host "MQL5 sincronizado e compilado com sucesso."
Write-Host "Proveniência: $provenance"
Write-Host "Fonte: $source"
Write-Host "Destino: $destination"
Write-Host "MetaEditor: $MetaEditorPath"
