$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$HostDir = Join-Path $Root 'windows-host'
$Port = 4173

Write-Host ''
Write-Host 'CONTROL HUB — PREVIA ORIGINAL DO FIGMA + OVERLAY PARA MT5' -ForegroundColor Cyan
Write-Host 'O painel original nao sera editado. REAL continua bloqueado.' -ForegroundColor Yellow
Write-Host ''

$node = Get-Command node -ErrorAction SilentlyContinue
$pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
$dotnet = Get-Command dotnet -ErrorAction SilentlyContinue
if (-not $node) { throw 'Node.js nao encontrado. Instale Node.js LTS e abra este script novamente.' }
if (-not $pnpm) { throw 'pnpm nao encontrado. Instale com: corepack enable; corepack prepare pnpm@latest --activate' }
if (-not $dotnet) { throw '.NET 8 SDK nao encontrado. Instale o SDK .NET 8 para Windows e execute novamente.' }

$runtime = Get-Process -Name terminal64 -ErrorAction SilentlyContinue
if (-not $runtime) { Write-Warning 'O terminal64.exe do MT5 nao parece estar aberto. Abra o MT5 antes de validar a sobreposicao.' }

if (-not (Test-Path (Join-Path $Root 'node_modules'))) {
  Write-Host 'Dependencias web ausentes; tentando instalar pelo lockfile...' -ForegroundColor Yellow
  Push-Location $Root
  try { pnpm install --frozen-lockfile } finally { Pop-Location }
}

$existing = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if (-not $existing) {
  $viteArgs = @('/c', 'cd /d "' + $Root + '" && pnpm exec vite --host 127.0.0.1 --port ' + $Port + ' --strictPort')
  Start-Process -FilePath 'cmd.exe' -ArgumentList $viteArgs -WindowStyle Normal
  $ready = $false
  for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    try { $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { $ready = $true; break } } catch {}
  }
  if (-not $ready) { throw "A previa do Figma nao respondeu na porta $Port. Confira a janela do Vite e a conexao de rede para baixar dependencias." }
} else {
  # Nao reutilizar silenciosamente outro servico que esteja usando a porta.
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 3
    $html = [string]$r.Content
    if ($r.StatusCode -ne 200 -or $html -notmatch '/src/main\.tsx' -or $html -notmatch 'id="root"') {
      throw "A porta $Port ja esta ocupada por um servico que nao parece ser a previa deste pacote. Feche esse servico ou libere a porta e execute novamente."
    }
    Write-Host "A previa Vite nesta porta responde com a estrutura esperada do projeto Figma." -ForegroundColor DarkYellow
  } catch {
    throw "Nao foi possivel confirmar que o servico na porta $Port pertence a este pacote. Para evitar abrir outro painel por engano, feche o servico da porta $Port e execute novamente. Detalhe: $($_.Exception.Message)"
  }
}

$env:CONTROLHUB_SYMBOL = ''
$env:CONTROLHUB_TIMEFRAME = '5m'
Write-Host 'Para ler automaticamente o grafico, compile e anexe mt5-bridge\ControlHubChartBridge.mq5 ao grafico desejado.' -ForegroundColor Yellow
Write-Host 'Sem a ponte MQL5 ativa, o painel nao presume qual ativo esta aberto e os sinais ficam indisponiveis.' -ForegroundColor Yellow

Push-Location $HostDir
try {
  Write-Host 'Iniciando o host de sobreposicao. Mantenha esta janela aberta durante o teste.' -ForegroundColor Green
  dotnet run
} finally { Pop-Location }
