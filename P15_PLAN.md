# P15 — Auditoria e segurança duráveis

## Objetivo

Completar a persistência operacional iniciada no P13/P14, tornando duráveis também a trilha de auditoria e o estado do kill switch.

## Escopo

- persistir `DecisionAudit` validado;
- restaurar a auditoria após reinício;
- persistir o estado do `KillSwitch`, incluindo motivo quando ativo;
- restaurar um kill switch ativo sem abrir uma janela insegura após reinício;
- integrar essa persistência ao `PersistentOperationalRecorder`;
- falhar fechado quando o estado de segurança persistido estiver inválido;
- manter `OperationMemoryStore` e a memória de operações compatíveis com P13/P14;
- manter execução, estratégia, risco e brokers fora do escopo.

## Critérios de validação

1. Auditorias permanecem disponíveis após recriar o recorder.
2. Kill switch ativo permanece ativo após reinício.
3. Desativação do kill switch também é persistida.
4. Estado de segurança inválido é rejeitado.
5. Suíte existente permanece verde.
6. Nenhuma execução REAL é liberada.
