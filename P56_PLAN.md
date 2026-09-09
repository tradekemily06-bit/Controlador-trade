# P56 — Uso controlado do conhecimento

## Objetivo
Criar uma fronteira explícita para que conhecimento confiável P55 possa ser marcado como elegível para uso controlado pelo ecossistema, sem alterar automaticamente estratégia, score, risco ou execução.

## Regras
- consumir somente conhecimento P55 válido;
- o uso deve ser explicitamente solicitado e identificável;
- preservar knowledge_id, hypothesis_id e test_id;
- produzir apenas uma autorização factual de uso, não uma ordem de operação;
- REAL permanece bloqueado e nenhuma execução é disparada;
- não alterar automaticamente estratégia, score ou risco;
- resultado imutável e determinístico;
- entradas inválidas falham fechado.

## Critério de encerramento
Existe uma fronteira entre conhecimento confiável e sua aplicação operacional controlada, mantendo rastreabilidade e impedindo que aprendizado se transforme diretamente em execução.
