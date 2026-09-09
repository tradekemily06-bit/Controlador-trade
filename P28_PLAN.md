# P28 — Execution Lifecycle Boundary

## Objetivo
Formalizar o ciclo de vida entre intenção admitida e resultado persistido, mantendo estados incertos como bloqueados até reconciliação.

## Regras
- PENDING não pode ser tratado como concluído;
- UNKNOWN não pode ser repetido automaticamente;
- ACCEPTED exige persistência coerente;
- REJECTED encerra o ciclo sem replay;
- qualquer inconsistência deve falhar fechado;
- nenhuma decisão de estratégia é alterada.

## Critério de encerramento
O ciclo de execução possui transições explícitas e testes para sucesso, rejeição, falha incerta e persistência inconsistente.
