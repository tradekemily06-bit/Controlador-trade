# P39 — Fronteira de risco pré-operação

## Objetivo
Criar uma avaliação determinística de risco antes da admissão de uma intenção DEMO, sem executar ordens e sem habilitar REAL.

## Regras
- validar quantidade, exposição atual e limites configurados;
- rejeitar valores negativos, não finitos ou configurações inválidas;
- separar avaliação de risco da execução;
- resultado imutável e fail-closed;
- limites inclusivos e determinísticos;
- não realizar retry, replay, rede ou chamadas a corretoras;
- REAL permanece bloqueado.

## Critério de encerramento
Existe uma fronteira testada que decide `APPROVED` ou `BLOCKED` para uma proposta de risco, sem executar qualquer operação.
