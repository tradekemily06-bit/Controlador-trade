# P46 — Ciclo de vida controlado da automação

## Objetivo
Representar deterministicamente o estado de um ciclo automatizado depois do handoff P44/P45, sem executar ou alterar estado externo.

## Estados
`CREATED → ADMITTED → DISPATCHED → COMPLETED` e `CREATED/ADMITTED/DISPATCHED → BLOCKED`.

## Regras
- transições explícitas e monotônicas;
- nenhum salto para estado terminal inválido;
- estados terminais não podem ser reutilizados;
- REAL nunca é permitido;
- cada transição produz um novo snapshot imutável;
- sem timers, threads, retries automáticos, rede, corretora ou execução;
- entradas inválidas falham fechado.

## Critério de encerramento
Existe uma máquina de estados pequena, determinística e testada para o ciclo automatizado, preparando rastreabilidade sem transformar estado de ciclo em execução.
