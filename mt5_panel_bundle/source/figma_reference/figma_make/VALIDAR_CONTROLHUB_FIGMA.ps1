$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Failures = 0
function Check($Label, $Ok, $Detail) {
  if ($Ok) { Write-Host "[OK] $Label — $Detail" -ForegroundColor Green }
  else { Write-Host "[PENDENTE] $Label — $Detail" -ForegroundColor Yellow; $script:Failures++ }
}
Write-Host ''
Write-Host 'CONTROL HUB — VALIDACAO SEM ALTERAR O PAINEL FIGMA' -ForegroundColor Cyan
Write-Host 'Somente leitura: compara todos os arquivos originais e verifica pre-requisitos/servicos. Nao envia ordens.' -ForegroundColor Gray
$Manifest = Join-Path $Root 'FIGMA_ORIGINAL_SHA256_MANIFEST.txt'
$ManifestOk = Test-Path -LiteralPath $Manifest
Check 'Manifesto de integridade' $ManifestOk 'hashes derivados do ZIP original'
if ($ManifestOk) {
  $Lines = Get-Content -LiteralPath $Manifest | Where-Object { $_ -match '^[A-Fa-f0-9]{64}  ' }
  $Checked = 0
  foreach ($Line in $Lines) {
    $Expected = $Line.Substring(0,64).ToUpperInvariant()
    $Relative = $Line.Substring(66)
    $Path = Join-Path $Root $Relative
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
      Check "Arquivo original $Relative" $false 'ausente'
      continue
    }
    $Actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
    Check "Arquivo original $Relative" ($Actual -eq $Expected) $(if ($Actual -eq $Expected) { 'SHA-256 idêntico ao ZIP original' } else { "SHA-256 diferente: $Actual" })
    $Checked++
  }
  Check 'Cobertura do manifesto' ($Lines.Count -eq 27 -and $Checked -eq 27) "entradas no manifesto: $($Lines.Count); arquivos encontrados: $Checked; esperado: 27"
}
foreach ($Name in @('node','pnpm','dotnet')) {
  $Cmd = Get-Command $Name -ErrorAction SilentlyContinue
  Check "Pre-requisito $Name" ([bool]$Cmd) $(if ($Cmd) { $Cmd.Source } else { 'nao instalado ou fora do PATH' })
}
$Mt5 = Get-Process -Name terminal64 -ErrorAction SilentlyContinue
Check 'MetaTrader 5 aberto' ([bool]$Mt5) $(if ($Mt5) { 'processo terminal64 encontrado' } else { 'abra o MT5 em DEMO para o teste visual' })
$Bridge = Join-Path $Root 'mt5-bridge\ControlHubChartBridge.mq5'
Check 'EA auxiliar de contexto' (Test-Path -LiteralPath $Bridge) 'EA apenas publica simbolo/periodo; nao envia ordens'
try {
  $Health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 3
  $Healthy = ($Health.ok -eq $true)
  Check 'Runtime local' $Healthy $(if ($Healthy) { 'API respondeu ok=true' } else { 'API respondeu, mas nao confirmou ok=true' })
} catch { Check 'Runtime local' $false 'API nao respondeu em http://127.0.0.1:8000/api/health' }
Write-Host ''
if ($Failures -eq 0) {
  Write-Host 'VERIFICACOES DISPONIVEIS PASSARAM. Isso nao comprova compilacao nem integracao nativa no grafico.' -ForegroundColor Green
} else {
  Write-Host "$Failures verificacao(oes) pendente(s). Nenhum arquivo foi alterado." -ForegroundColor Yellow
}
Write-Host 'REAL permanece desabilitado; use apenas DEMO/SIMULACAO.' -ForegroundColor Yellow
