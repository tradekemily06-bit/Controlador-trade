# Stages 3–7 — mapa de avanço paralelo

## Regra principal

A Stage 2 permanece aberta e inalterada enquanto este trabalho avança. Nenhum gate da Stage 2 é fechado, nenhum PR é mergeado e nenhum trabalho das Stages 3–7 pode enfraquecer suas barreiras.

## Stage 3 — Production Readiness / DEMO

Objetivo: transformar a integração DEMO em uma fronteira operacional verificável, sem aumentar a capacidade REAL.

Gates:
- contrato comum `ExecutionRequest`/`ExecutionResult`;
- adapter DEMO isolado do motor de decisão;
- conta DEMO e símbolo confirmados;
- cotação válida e volume válido;
- `order_check()` antes de `order_send()`;
- external ID preservado;
- rejeições e respostas não confirmadas tratadas fail-closed;
- kill switch/incidente/duplicidade/frescor/restart cobertos;
- reconciliação e auditoria com evidência;
- secrets fora do código/repositório.

## Stage 4 — Reliability / Recovery / Multi-instance

Objetivo: provar que o ecossistema continua seguro sob restart, falhas parciais, concorrência e múltiplas instâncias.

Gates:
- estado operacional durável e atomicamente recuperável;
- startup fail-closed diante de estado ausente/corrompido/inconsistente;
- locks e idempotência cross-process;
- recuperação de UNKNOWN sem duplicação;
- reconciliação depois de restart;
- testes de concorrência entre processos/instâncias;
- isolamento de estado por instalação/tenant quando aplicável;
- health checks informativos não podem virar autorização de execução.

## Stage 5 — Observability / Audit / Operations

Objetivo: tornar o sistema operacionalmente explicável e auditável sem expor secrets ou poluir a operação.

Gates:
- eventos de segurança e execução com correlação por request ID;
- trilha de decisão → risco → gateway → adapter → resultado → reconciliação;
- métricas de bloqueio, UNKNOWN, rejeição, latência e recuperação;
- alertas para eventos realmente importantes;
- retenção e redaction de dados sensíveis;
- diagnóstico seguro e legível;
- runbooks de incidente, kill switch, restart e reconciliação;
- observabilidade não pode alterar decisão nem bypassar barreiras.

## Stage 6 — Product / UX / Learning / SaaS boundaries

Objetivo: consolidar a experiência do ecossistema sem misturar operação, aprendizagem, memória e administração.

Gates:
- separação clara Operação / Análise / Memória / Laboratório / Ensino;
- onboarding que explica onde cada recurso está sem bloquear a operação;
- notificações de eventos importantes sem excesso de ruído;
- preferências e memória não alteram autorização financeira;
- estado de segurança sempre visível quando relevante;
- tenant/user isolation nas superfícies persistentes;
- API/UI não podem criar privilégios de execução;
- mobile-first preservado.

## Stage 7 — Release Governance / Controlled REAL Readiness

Objetivo: preparar uma revisão independente e rastreável para eventual habilitação controlada, sem habilitar REAL automaticamente.

Gates:
- todas as stages anteriores com evidência executável;
- matriz de segurança e side-door scan atualizados;
- recuperação/reconciliação comprovadas;
- integração DEMO estável;
- secrets/configuração de produção revisados;
- threat model e incident response revisados;
- release checklist e rollback definidos;
- separação explícita entre DEMO e REAL;
- REAL continua bloqueado até uma decisão posterior e explícita.

## Ordem de execução paralela

1. Stage 3: fortalecer DEMO e contratos de integração.
2. Stage 4: transformar restart/concurrency/recovery em gates executáveis.
3. Stage 5: consolidar observabilidade e auditoria operacional.
4. Stage 6: consolidar UX/SaaS/ensino sem criar side doors.
5. Stage 7: preparar o pacote de release e revisão controlada.
6. Em paralelo, Stage 2 continua aberta para receber os achados que surgirem dessas etapas.

## Proibição

Nenhuma Stage 3–7 pode:
- habilitar REAL;
- criar um executor paralelo fora do gateway;
- substituir o barrier autoritativo;
- reconstruir autorização/admissão privilegiada por serializer/copy/factory;
- usar UI, API, health check ou configuração como bypass;
- considerar CI ou uma ordem DEMO isolada como prova suficiente para REAL.
