# Preparação antecipada — Stages 4, 5 e 6

Este documento antecipa trabalho das próximas stages sem alterar a autoridade de execução da Stage 3 e sem habilitar REAL.

## Regra de prioridade

- Stage 3 continua sendo a frente principal e o gate operacional atual.
- Stage 4 trata recuperação e consistência após falhas.
- Stage 5 trata observabilidade, auditoria e notificações.
- Stage 6 trata experiência/produto, onboarding, laboratório, memória, aprendizado e isolamento SaaS.
- Nenhuma preparação desta documentação pode substituir ou enfraquecer uma barreira anterior.

## Stage 4 — Reliability / Recovery

### Alvos já existentes para auditoria

- `core/runtime_checkpoint.py`
- `core/recovery_coordinator.py`
- `core/recovery_policy.py`
- `execution/execution_lifecycle.py`
- `execution/execution_ledger.py`
- `core/file_lock.py`

### Matriz antecipada

1. restart com `PENDING`;
2. restart com `RESERVED`;
3. restart com `UNKNOWN`;
4. divergência ledger/lifecycle;
5. divergência checkpoint/lifecycle;
6. JSON ausente, truncado ou inválido;
7. falha de persistência no meio do ciclo;
8. crash antes do dispatch;
9. crash após possível dispatch;
10. dois processos com o mesmo `request_id`;
11. reconciliação explícita sem replay automático;
12. tentativa de regressão de estado terminal.

### Critério de saída

Todo estado ambíguo deve permanecer bloqueado até reconciliação explícita. Recovery não pode inventar resultado, reenviar ordem automaticamente ou restaurar privilégio REAL.

## Stage 5 — Observability / Audit / Notifications

### Componentes já existentes para auditoria

- `core/p21_observability.py`
- `core/operational_alerts.py`
- `core/ecosystem_notifications.py`
- gerenciadores de incidentes e manutenção
- recorder/auditoria operacional

### Matriz antecipada

1. eventos de execução aceitos/rejeitados/UNKNOWN;
2. eventos de recovery e reconciliação;
3. incidentes CRITICAL/IMPORTANT/INFO;
4. redaction de segredos e dados sensíveis;
5. correlação entre request, decisão, execução e auditoria;
6. notificações sem capacidade de autorizar execução;
7. atualizações do ecossistema sem interromper silenciosamente uma operação;
8. persistência e consulta histórica;
9. isolamento de eventos entre tenants;
10. comportamento seguro quando observabilidade estiver indisponível.

### Critério de saída

Observabilidade deve explicar o que aconteceu sem ganhar autoridade para executar. Falhas de logging/auditoria não podem criar um caminho alternativo de execução.

## Stage 6 — Product / Ecosystem

### Componentes já existentes para auditoria

- `core/ecosystem_onboarding.py`
- `web/components/onboarding.html`
- `web/components/onboarding.js`
- `test_onboarding_api.py`
- `tests/test_ecosystem_onboarding.py`
- camada de identidade/tenant e armazenamento de produção
- módulos de memória, aprendizagem, laboratório/replay e experiência

### Matriz antecipada

1. primeiro uso e Modo de Usar;
2. Operação, Análise e Memória sem duplicação/confusão;
3. laboratório/replay isolado da operação;
4. memória de aprendizado sem mutação silenciosa da estratégia;
5. estatísticas diárias/semanais/mensais com origem rastreável;
6. notificações importantes sem poluir a operação;
7. atualizações visíveis e seguras;
8. isolamento por tenant/usuário;
9. preferências sem alterar barreiras de segurança;
10. experiência mobile sem criar bypass da camada de segurança.

### Critério de saída

A camada de produto pode orientar, ensinar, explicar e organizar, mas não pode autorizar execução por conta própria nem contaminar estado operacional com dados de laboratório/replay.

## Dependências entre stages

`Stage 3 -> Stage 4 -> Stage 5 -> Stage 6 -> Stage 7`

A preparação pode ocorrer em paralelo, mas a liberação de cada stage depende dos gates anteriores. Stage 7 continua sendo a auditoria final de todo o ecossistema.
