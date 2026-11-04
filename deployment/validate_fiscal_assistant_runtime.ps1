param(
    [string]$BaseUrl = 'http://127.0.0.1:8000'
)

$ErrorActionPreference = 'Stop'
$identity = [string]$env:CONTROLADOR_SINGLE_USER_IDENTITY
if ([string]::IsNullOrWhiteSpace($identity)) {
    throw 'CONTROLADOR_SINGLE_USER_IDENTITY ausente. Configure a identidade autorizada no ambiente Windows; o valor não será exibido.'
}

$BaseUrl = $BaseUrl.TrimEnd('/')
$headers = @{ 'Cf-Access-Authenticated-User-Email' = $identity }
$checks = New-Object System.Collections.Generic.List[object]

function Add-Check([string]$Name, [bool]$Ok, [string]$Detail) {
    $checks.Add([pscustomobject]@{ check = $Name; ok = $Ok; detail = $Detail })
}

function Get-LocalJson([string]$Path) {
    $response = Invoke-WebRequest -UseBasicParsing -Method Get -Uri ($BaseUrl + $Path) -Headers $headers -TimeoutSec 8 -ErrorAction Stop
    if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 300) {
        throw "HTTP inesperado em $Path: $($response.StatusCode)"
    }
    return ($response.Content | ConvertFrom-Json)
}

try {
    $health = Get-LocalJson '/api/health'
    $safe = (
        $health.ok -eq $true -and
        $health.execution_allowed -eq $false -and
        $health.real -eq 'DESABILITADO' -and
        $null -ne $health.operational_observability.execution -and
        $health.operational_observability.execution.allowed -eq $false -and
        $health.operational_observability.execution.real -eq 'DISABLED' -and
        $null -ne $health.real_runtime -and
        $health.real_runtime.real_execution_allowed -eq $false -and
        $health.real_runtime.explicitly_enabled -eq $false
    )
    Add-Check 'runtime-health-demo-safe' $safe 'Health consultado; execução REAL permanece bloqueada.'
} catch {
    Add-Check 'runtime-health-demo-safe' $false 'Health local indisponível ou contrato de segurança inválido.'
}

try {
    $fiscal = Get-LocalJson '/api/fiscal-reserve?limit=1'
    $foreignSafe = (
        $null -ne $fiscal.foreign_pending -and
        $fiscal.foreign_pending.included_in_totals -eq $false -and
        $fiscal.foreign_pending.reserve_calculated -eq $false
    )
    Add-Check 'fiscal-reserve-owner-scope' ($null -ne $fiscal.periods -and $foreignSafe) 'Resumo fiscal e fronteira de pendências estrangeiras consultados; nenhum registro foi alterado.'
} catch {
    Add-Check 'fiscal-reserve-owner-scope' $false 'Resumo fiscal indisponível ou fronteira de pendências não segura.'
}

try {
    $domestic = Get-LocalJson '/api/fiscal-reserve/domestic-pending/summary'
    Add-Check 'domestic-pending-read-only' ($null -ne $domestic) 'Resumo da fila brasileira consultado sem classificação ou lançamento.'
} catch {
    Add-Check 'domestic-pending-read-only' $false 'Resumo de pendências brasileiras indisponível.'
}

try {
    $foreign = Get-LocalJson '/api/fiscal-reserve/pending?limit=1'
    Add-Check 'foreign-pending-read-only' ($null -ne $foreign.items -and $foreign.total -ge 0) 'Fila estrangeira consultada; registros continuam pendentes e fora da reserva.'
} catch {
    Add-Check 'foreign-pending-read-only' $false 'Fila de pendências estrangeiras indisponível.'
}

try {
    $assistant = Get-LocalJson '/api/assistant/status'
    $safeAssistant = (
        $assistant.read_only -eq $true -and
        $assistant.may_execute_orders -eq $false -and
        $assistant.may_enable_real -eq $false -and
        $assistant.may_move_money -eq $false -and
        $assistant.PSObject.Properties.Name -notcontains 'OPENAI_API_KEY'
    )
    $providerState = if ($assistant.connection_tested -eq $true) { 'conexão reportada como testada' } elseif ($assistant.available -eq $true) { 'credenciais configuradas; conexão ainda não testada' } else { 'provedor indisponível; nenhuma chamada foi feita' }
    Add-Check 'assistant-read-only-status' $safeAssistant "Status consultado sem chamar o provedor; $providerState."
} catch {
    Add-Check 'assistant-read-only-status' $false 'Status do Assistente indisponível ou contrato de segurança inválido.'
}

$failed = @($checks | Where-Object { -not $_.ok })
$result = [pscustomobject]@{
    generated_at = (Get-Date).ToUniversalTime().ToString('o')
    base_url = $BaseUrl
    checks = $checks
    passed = ($checks.Count - $failed.Count)
    failed = $failed.Count
    ready = ($failed.Count -eq 0)
    note = 'Somente GET local. Nenhuma chave, conversa, ordem, lançamento fiscal ou chamada paga foi criada.'
}
$result | ConvertTo-Json -Depth 5
if ($failed.Count -gt 0) { exit 2 }
exit 0
