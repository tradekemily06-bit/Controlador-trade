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
        throw "HTTP inesperado em ${Path}: $($response.StatusCode)"
    }
    return ($response.Content | ConvertFrom-Json)
}

function Test-RejectedIdentity([string]$Path) {
    $invalidHeaders = @{ 'Cf-Access-Authenticated-User-Email' = 'unauthorized-smoke-identity@example.invalid' }
    try {
        Invoke-WebRequest -UseBasicParsing -Method Get -Uri ($BaseUrl + $Path) -Headers $invalidHeaders -TimeoutSec 8 -ErrorAction Stop | Out-Null
        return $false
    } catch {
        $response = $_.Exception.Response
        if ($null -eq $response) { return $false }
        return ([int]$response.StatusCode -eq 403)
    }
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
    $periodNames = @($fiscal.periods.PSObject.Properties.Name)
    $requiredPeriods = @('day', 'week', 'month', 'year')
    $periodsComplete = @($requiredPeriods | Where-Object { $periodNames -contains $_ }).Count -eq 4
    $semanticsSafe = (
        $fiscal.reserve_semantics.kind -eq 'PLANNING_ESTIMATE_ONLY' -and
        $fiscal.reserve_semantics.tax_liability_confirmed -eq $false -and
        $fiscal.reserve_semantics.monthly_tax_assessment -eq $false -and
        $fiscal.reserve_semantics.monthly_loss_offsets_calculated -eq $false -and
        $fiscal.reserve_semantics.irrf_credits_calculated -eq $false -and
        $fiscal.reserve_semantics.positive_entry_only -eq $true
    )
    $fiscalSafe = (
        $periodsComplete -and $semanticsSafe -and
        $fiscal.currency -eq 'BRL' -and
        $fiscal.total_reserved_brl -ge 0 -and $foreignSafe
    )
    Add-Check 'fiscal-reserve-owner-scope-and-estimate-boundary' $fiscalSafe 'Períodos, moeda, estimativa não tributária e exclusão de pendências estrangeiras verificados; nenhum registro foi alterado.'
} catch {
    Add-Check 'fiscal-reserve-owner-scope' $false 'Resumo fiscal indisponível ou fronteira de pendências não segura.'
}

try {
    $domestic = Get-LocalJson '/api/fiscal-reserve/domestic-pending/summary'
    $domesticPeriods = @($domestic.periods.PSObject.Properties.Name)
    $requiredPeriods = @('day', 'week', 'month', 'year')
    $domesticSafe = (
        $domestic.available -eq $true -and
        $domestic.classification_status -eq 'PENDING_CLASSIFICATION' -and
        $domestic.included_in_totals -eq $false -and
        $domestic.reserve_calculated -eq $false -and
        @($requiredPeriods | Where-Object { $domesticPeriods -contains $_ }).Count -eq 4
    )
    Add-Check 'domestic-pending-read-only' $domesticSafe 'Fila brasileira owner-scoped, pendente, sem classificação automática ou lançamento; períodos conferidos.'
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

try {
    $assistantDenied = Test-RejectedIdentity '/api/assistant/status'
    $fiscalDenied = Test-RejectedIdentity '/api/fiscal-reserve/pending?limit=1'
    Add-Check 'unauthorized-identity-denied' ($assistantDenied -and $fiscalDenied) 'Identidade sintética não autorizada recebeu HTTP 403 nos dois módulos.'
} catch {
    Add-Check 'unauthorized-identity-denied' $false 'Não foi possível confirmar a rejeição da identidade sintética.'
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
