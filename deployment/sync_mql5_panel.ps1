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

function Restore-File([string]$Backup, [string]$Target) {
    if (Test-Path -LiteralPath $Backup -PathType Leaf) {
        Copy-WithRetry -Source $Backup -Destination $Target
    } elseif (Test-Path -LiteralPath $Target -PathType Leaf) {
        Remove-Item -LiteralPath $Target -Force -ErrorAction SilentlyContinue
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
    # O caminho real informado pela ponte MT5 é a referência principal.
    # Não inferir o perfil de dados apenas porque ele contém arquivos do EA.
    $paths = Get-Mt5Paths -TerminalPath $TerminalPath
    if (-not $paths -or [string]::IsNullOrWhiteSpace([string]$paths.data_path)) {
        throw 'Não foi possível confirmar a pasta de dados da instância MT5 conectada pela ponte Python.'
    }
    $bridgeDataPath = [System.IO.Path]::GetFullPath([string]$paths.data_path)
    if (-not (Test-Path -LiteralPath $bridgeDataPath -PathType Container) -or
        -not (Test-Path -LiteralPath (Join-Path $bridgeDataPath 'MQL5') -PathType Container)) {
        throw "A ponte MT5 retornou uma pasta de dados inválida: $bridgeDataPath"
    }

    if (-not [string]::IsNullOrWhiteSpace($RequestedPath)) {
        $requested = [System.IO.Path]::GetFullPath($RequestedPath)
        if (-not (Test-Path -LiteralPath $requested -PathType Container) -or
            -not (Test-Path -LiteralPath (Join-Path $requested 'MQL5') -PathType Container)) {
            throw "Pasta de dados MT5 configurada inválida (pasta ou MQL5 ausente): $requested"
        }
        if (-not [string]::Equals($requested, $bridgeDataPath, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Destino bloqueado: CONTROLADOR_MT5_DATA_PATH ($requested) não corresponde à pasta retornada pela instância MT5 conectada ($bridgeDataPath). Nenhum arquivo foi sincronizado."
        }
        return $bridgeDataPath
    }

    # Uma única pasta com o EA não prova que ela pertence à instância conectada.
    # Se houver uma candidata, ela deve coincidir com a pasta da ponte; se houver
    # várias, não escolher automaticamente. A ausência de candidatas permite usar
    # somente o data_path que a própria ponte MT5 acabou de informar.
    $profilesRoot = Join-Path $env:APPDATA 'MetaQuotes\Terminal'
    $candidates = @()
    if (Test-Path -LiteralPath $profilesRoot -PathType Container) {
        foreach ($profile in @(Get-ChildItem -LiteralPath $profilesRoot -Directory -ErrorAction SilentlyContinue)) {
            $eaDir = Join-Path $profile.FullName 'MQL5\Experts\ControladorTrading'
            $sourcePresent = Test-Path -LiteralPath (Join-Path $eaDir 'Controlador-Trading.mq5') -PathType Leaf
            $binaryPresent = Test-Path -LiteralPath (Join-Path $eaDir 'Controlador-Trading.ex5') -PathType Leaf
            if ($sourcePresent -or $binaryPresent) {
                $candidates += [System.IO.Path]::GetFullPath($profile.FullName)
            }
        }
    }
    $candidates = @($candidates | Sort-Object -Unique)
    if ($candidates.Count -gt 1) {
        throw "Mais de uma pasta de dados contém o painel; configure CONTROLADOR_MT5_DATA_PATH com o caminho exato da instância conectada. Nenhum arquivo foi sincronizado: $($candidates -join '; ')"
    }
    if ($candidates.Count -eq 1 -and
        -not [string]::Equals($candidates[0], $bridgeDataPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Destino bloqueado: a única pasta com o painel ($($candidates[0])) não corresponde à pasta de dados retornada pela instância conectada ($bridgeDataPath). Nenhum arquivo foi sincronizado."
    }

    # Mesmo com processos duplicados, nunca escolher uma pasta por heurística:
    # usar apenas o data_path efetivamente reportado pela ponte, após a comparação
    # acima com a configuração explícita ou com a única pasta que contém o EA.
    return $bridgeDataPath
}

$dataPath = Resolve-Mt5DataPath -RequestedPath $Mt5DataPath -TerminalPath $Mt5TerminalPath
$terminalInstallPath = Split-Path -Parent $Mt5TerminalPath
$destinationDir = Join-Path $dataPath 'MQL5\Experts\ControladorTrading'
$destination = Join-Path $destinationDir 'Controlador-Trading.mq5'
New-Item -ItemType Directory -Force -Path $destinationDir | Out-Null

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

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupSource = "$destination.$stamp.bak"
$backupBinary = [System.IO.Path]::ChangeExtension($destination, '.ex5') + ".$stamp.bak"
$backupProvenance = "$provenance.$stamp.bak"
if (Test-Path -LiteralPath $destination) { Copy-WithRetry -Source $destination -Destination $backupSource }
if (Test-Path -LiteralPath $binary) { Copy-WithRetry -Source $binary -Destination $backupBinary }
if (Test-Path -LiteralPath $provenance) { Copy-WithRetry -Source $provenance -Destination $backupProvenance }

Copy-WithRetry -Source $source -Destination $destination
$copiedSourceHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
if ($copiedSourceHash -ne $sourceHash) {
    Restore-File -Backup $backupSource -Target $destination
    Restore-File -Backup $backupBinary -Target $binary
    Restore-File -Backup $backupProvenance -Target $provenance
    throw "A fonte mudou durante a sincronização; destino restaurado: $destination"
}

$log = [System.IO.Path]::ChangeExtension($destination, '.log')
if (Test-Path -LiteralPath $log) { Remove-Item -LiteralPath $log -Force }
$compileStartedAt = Get-Date
$explicitLog = $log
$binaryHashBefore = if (Test-Path -LiteralPath $binary -PathType Leaf) { (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash } else { '' }

& $MetaEditorPath "/compile:$destination" "/log:$explicitLog" | Out-Null
$metaEditorExitCode = $LASTEXITCODE
Start-Sleep -Milliseconds 500
if (-not (Test-Path -LiteralPath $log -PathType Leaf)) {
    Restore-File -Backup $backupSource -Target $destination
    Restore-File -Backup $backupBinary -Target $binary
    Restore-File -Backup $backupProvenance -Target $provenance
    throw "MetaEditor não produziu log de compilação: $log"
}

$logText = Get-Content -LiteralPath $log -Raw -ErrorAction SilentlyContinue
$errorMatch = [regex]::Match($logText, '(?i)(\d+)\s+(errors?|erros?)')
$warningMatch = [regex]::Match($logText, '(?i)(\d+)\s+(warnings?|avisos?)')
if (-not $errorMatch.Success -or -not $warningMatch.Success) {
    Restore-File -Backup $backupSource -Target $destination
    Restore-File -Backup $backupBinary -Target $binary
    Restore-File -Backup $backupProvenance -Target $provenance
    throw "Log de compilação sem contagem inequívoca de erros/avisos: $log"
}
$errors = $errorMatch.Groups[1].Value
$warnings = $warningMatch.Groups[1].Value
if ($errors -ne '0' -or $warnings -ne '0') {
    Restore-File -Backup $backupSource -Target $destination
    Restore-File -Backup $backupBinary -Target $binary
    Restore-File -Backup $backupProvenance -Target $provenance
    throw "Compilação MQL5 rejeitada: errors=$errors warnings=$warnings. Log: $log"
}

if (-not (Test-Path -LiteralPath $binary -PathType Leaf)) {
    Restore-File -Backup $backupSource -Target $destination
    Restore-File -Backup $backupBinary -Target $binary
    Restore-File -Backup $backupProvenance -Target $provenance
    throw "MetaEditor terminou sem gerar o EX5 esperado: $binary"
}

$binaryWriteTime = (Get-Item -LiteralPath $binary).LastWriteTime
$binaryHashAfter = (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash
if ($binaryWriteTime -lt $compileStartedAt.AddSeconds(-2)) {
    Restore-File -Backup $backupSource -Target $destination
    Restore-File -Backup $backupBinary -Target $binary
    Restore-File -Backup $backupProvenance -Target $provenance
    throw "O EX5 não foi atualizado pela compilação (timestamp anterior à compilação): $binary"
}

$provenanceTemp = "$provenance.$stamp.tmp"
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
    Restore-File -Backup $backupSource -Target $destination
    Restore-File -Backup $backupBinary -Target $binary
    Restore-File -Backup $backupProvenance -Target $provenance
    Remove-Item -LiteralPath $provenanceTemp -Force -ErrorAction SilentlyContinue
    throw "Não foi possível registrar a proveniência da compilação; arquivos anteriores restaurados. $($_.Exception.Message)"
}

if ($metaEditorExitCode -ne 0) {
    Write-Warning "MetaEditor retornou código $metaEditorExitCode, mas o log confirmou 0 erros/avisos e o EX5 foi atualizado. Resultado validado pelos artefatos."
}

Remove-Item -LiteralPath $log -Force -ErrorAction SilentlyContinue
# Preserve os backups datados para recuperação manual após validação no MT5.
Write-Host "Backups preservados para recuperação:"
if (Test-Path -LiteralPath $backupSource -PathType Leaf) { Write-Host "Fonte anterior: $backupSource" }
if (Test-Path -LiteralPath $backupBinary -PathType Leaf) { Write-Host "EX5 anterior: $backupBinary" }
if (Test-Path -LiteralPath $backupProvenance -PathType Leaf) { Write-Host "Proveniência anterior: $backupProvenance" }

Write-Host "MQL5 sincronizado e compilado com sucesso."
Write-Host "Proveniência: $provenance"
Write-Host "Fonte: $source"
Write-Host "Destino: $destination"
Write-Host "MetaEditor: $MetaEditorPath"
