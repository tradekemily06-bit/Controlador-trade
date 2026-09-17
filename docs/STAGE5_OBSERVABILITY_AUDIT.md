# Stage 5 — Observability, Audit & Operations

Stage 5 transforma o comportamento interno em evidência operacional sem criar qualquer caminho de execução paralelo.

## Gates

- correlation/request ID atravessa decisão, risco, gateway, adapter, ledger e reconciliação;
- eventos de BLOCKED, UNKNOWN, ACCEPTED, RECONCILED e incidentes são distinguíveis;
- logs e auditoria redigem secrets, tokens e credenciais;
- métricas não dependem de dados sensíveis nem alteram decisões;
- alertas priorizam incidentes, bloqueios críticos, UNKNOWN e falhas de recuperação;
- retenção é limitada e adequada ao tipo de evento;
- diagnóstico pode explicar por que uma operação foi bloqueada;
- runbooks existem para kill switch, incidente, restart e reconciliação;
- observabilidade nunca pode ser usada como autorização.

## Evidência

Os contratos devem ser testados com eventos reais do fluxo de teste, incluindo bloqueio, falha, restart e reconciliação. Qualquer componente de observabilidade que falhar durante uma decisão deve preservar a barreira de segurança.
