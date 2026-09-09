# P49 — Reconciliação controlada do resultado

## Objetivo
Comparar um resultado factual P48 com uma observação externa explicitamente fornecida, detectando correspondência, divergência ou ausência sem acessar corretora, rede ou persistência.

## Regras
- consumir somente resultado P48 válido;
- aceitar somente observação externa explicitamente fornecida;
- comparar identificadores e fatos sem reinterpretá-los;
- estados `MATCHED`, `MISMATCHED` e `UNVERIFIED`;
- divergência nunca é corrigida automaticamente;
- ausência de referência externa permanece não verificada;
- não executar, repetir ou reconciliar via rede/corretora;
- não alterar ledger, risco, memória ou auditoria persistida;
- resultado imutável e determinístico;
- entradas inválidas falham fechado.

## Critério de encerramento
Existe uma fronteira que torna a reconciliação uma decisão factual e explícita, sem permitir que uma divergência seja silenciosamente convertida em resultado confiável.
