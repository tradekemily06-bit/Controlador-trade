# Multi-replica market-data deployment boundary

## Current supported topology

The standalone market-data runtime currently uses SQLite for tenant-scoped provider connection metadata, candle-close watch subscriptions and analysis results, processing leases and notification outbox rows, and OAuth state/token metadata (ciphertext only for tokens).

The timeframe processing lease and notification outbox coordinate correctly only when all workers access the same SQLite database file on storage with SQLite-compatible locking semantics. A local process lock also prevents two standalone runtime owners from opening the same runtime directory concurrently.

This is a single-host / single-runtime deployment boundary. Do not scale the application by starting multiple containers with separate local volumes and assume duplicate work or notification delivery is coordinated.

The runtime now fails closed when `CONTROLADOR_EXPECTED_REPLICAS` is greater
than `1`. The default is `1`; invalid or non-positive values also stop
startup. This is an explicit operator declaration, not automatic replica
discovery. The local readiness response exposes the enforced topology, while
remote readiness reveals only the non-sensitive deployment boundary.

This guard prevents a declared multi-replica deployment from silently running
on local SQLite. It does not implement PostgreSQL or make the system
multi-replica ready. Remove the guard only as part of a tested shared-storage
migration that satisfies every release gate below.

## Required before multi-host / multi-replica production

1. Move tenant metadata, watch subscriptions, results, processing leases and notification outbox to one shared transactional database (recommended: PostgreSQL).
2. Keep tenant and subject identifiers in every ownership predicate. Use database row-level security where practical, but retain application-level trusted-context checks.
3. Acquire a processing lease atomically using a unique watch key and an expiring owner token. Renew only while the same token owns an unexpired lease. Fence result persistence in the same transaction that inserts the result and outbox event.
4. Claim outbox rows transactionally with PostgreSQL `FOR UPDATE SKIP LOCKED` (or an equivalent atomic claim). Persist attempt count and lease expiry. Keep stable event IDs and require downstream deduplication because delivery is at-least-once, not exactly-once.
5. Use a distributed lease backend for cTrader OAuth refresh. The current injected lease-provider contract must be backed by the same shared coordination service across all replicas.
6. Move encrypted OAuth ciphertext and key metadata to durable shared storage; keep the encryption key in KMS/envelope encryption, never in the database or repository.
7. Ensure provider stream ownership is explicit. A replica restart must rehydrate subscriptions safely, and only one active stream owner per tenant/account/symbol/timeframe should publish accepted closed candles.
8. Add graceful worker shutdown, lease expiry recovery, database failover tests, and concurrent multi-replica tests before enabling horizontal scaling.

## Release gates

A multi-replica release is blocked until automated integration tests prove:
- two independent app replicas cannot analyze the same closed candle concurrently;
- a worker that loses its lease cannot persist a result or create an outbox event;
- a crashed worker's lease expires and another worker safely resumes;
- concurrent outbox consumers do not claim the same event simultaneously;
- retries preserve the same event ID and do not lose the durable analysis;
- tenant A cannot read, renew, release, or dispatch tenant B's work;
- OAuth refresh rotation is serialized across replicas;
- health/readiness reports a missing shared backend as unavailable rather than silently falling back to local coordination.

## Current product safety

Provider adapters remain read-only. A connected account is not considered operational until its provider handshake and fresh market data are verified. TradingView webhooks are event alerts, not continuous price feeds. A local MT5 relay requires its host terminal and machine to remain online. Closing the app window is not equivalent to shutting down the always-on worker host.

SIMULAÇÃO remains the default. Real order execution and money movement are outside this foundation and remain disabled.


## Fundação técnica — oito gates de conclusão

Este quadro é um contrato de aceite, não uma declaração de que os itens já estão concluídos. A classificação só muda quando houver evidência executável e verificável.

| Gate | Critério para considerar concluído | Situação comprovada nesta revisão |
|---|---|---|
| 1. Persistência compartilhada | PostgreSQL ou banco transacional compartilhado adotado por todos os repositórios críticos; migrações, isolamento por tenant, leases e outbox testados entre processos independentes | **Bloqueado**: os repositórios operacionais ainda usam SQLite local. O guard impede réplicas declaradas acima de uma; não existe backend PostgreSQL integrado |
| 2. Identidade e isolamento | Identidade autenticada emitida pelo servidor, tenant/subject derivados de claims verificados, autorização em todas as rotas e testes negativos entre tenants | **Parcial**: contratos de contexto confiável e escopo tenant/subject existem; configuração e validação de um provedor de identidade de produção ainda precisam ser feitas |
| 3. Segredos e KMS | KMS/envelope encryption real, rotação, revogação, política de acesso e recuperação de chaves testadas | **Parcial**: vaults e interfaces de cipher existem; KMS real é injetado pelo host e ainda não está provisionado/validado |
| 4. Notificações externas | Provedor real configurado, worker ativo, credenciais seguras, confirmação de entrega, retry/dead-letter e teste com cliente fechado | **Parcial**: outbox durável, worker e contratos de sink existem; o runtime padrão não configura provedor externo e não comprova push com o app fechado |
| 5. Recuperação de provedores | OAuth/refresh, reconexão e rebind após reinício testados com contas DEMO reais, com isolamento e status de saúde | **Parcial**: caminhos automatizados e testes com doubles existem; falta handshake real com contas e credenciais de DEMO |
| 6. Backup e restauração | Backup agendado e criptografado, cópia fora do host, retenção, alerta de falha e restauração integral ensaiada | **Parcial**: backup local/on-demand e agendamento configurável existem; cópia off-host, retenção operacional e restore drill ainda não foram comprovados |
| 7. Operação contínua | Host cloud/VPS 24/7, monitoramento, alertas, logs, health checks, restart/failover e atualização segura validados | **Pendente**: os workers acompanham o processo; não há implantação contínua de produção validada |
| 8. Provedores em DEMO | Cada conector aprovado faz handshake real, confirma conta DEMO, entrega candles/quotes atuais e passa teste de desconexão/retomada | **Parcial**: adaptadores e fluxos read-only foram implementados/testados automaticamente; não há evidência de sessão real DEMO neste ambiente |

### Regra de encerramento

- Nenhum gate será marcado como concluído apenas porque uma classe, endpoint, teste unitário ou variável de ambiente existe.
- Um teste com mock comprova o comportamento do código sob aquele cenário; não comprova credenciais, conectividade, limites ou disponibilidade do fornecedor real.
- A passagem de cada gate exige evidência no commit exato, e os gates 1, 3, 4, 6, 7 e 8 também exigem infraestrutura/contas externas configuradas.
- A interface Lovable permanece fora do escopo destas alterações. Nenhum merge, deploy, ordem ou movimentação financeira é autorizado por este documento.
