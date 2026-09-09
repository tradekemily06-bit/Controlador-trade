# P25 — Unified Safety Gate

## Objetivo
Unificar em uma fronteira somente leitura os sinais de segurança já existentes antes de considerar o runtime apto para execução DEMO.

## Regras
- REAL nunca fica READY;
- kill switch ativo bloqueia;
- recuperação que exige reconciliação bloqueia;
- dados de mercado não íntegros bloqueiam;
- configuração inválida bloqueia;
- nenhuma ordem é executada pelo gate.
