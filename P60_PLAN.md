# P60 — Proposta controlada de adaptação

## Objetivo
Criar a fronteira entre resultados de laboratório e uma proposta de adaptação do ecossistema, sem permitir alteração automática do núcleo operacional.

## Regras
- consumir somente resultado P59 válido;
- proposta deve manter origem e rastreabilidade;
- proposta não é alteração aplicada;
- nenhuma mudança automática de estratégia, score, risco ou execução;
- REAL permanece bloqueado;
- decisão de aplicação deve ocorrer fora desta fronteira e de forma explícita;
- imutável, determinístico e fail-closed.

## Critério de encerramento
O ciclo conhecimento → auditoria → laboratório → proposta de adaptação termina em uma fronteira segura, evitando que aprendizado experimental altere diretamente o comportamento operacional.
