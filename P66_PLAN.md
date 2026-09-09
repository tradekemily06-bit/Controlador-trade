# P66 — avaliação factual pós-adaptação

Objetivo: criar uma avaliação explícita da observação pós-ativação, sem transformar observação em prova automática de eficácia.

Regras:
- exige `AdaptationObservation` válido;
- status explícito: `SUPPORTED`, `NOT_SUPPORTED` ou `INCONCLUSIVE`;
- exige justificativa não vazia;
- preserva `proposal_id`, `application_id` e `observation_id`;
- imutável, determinístico e fail-closed;
- nenhuma inferência automática de causalidade ou lucro;
- não altera estratégia, score, risco ou execução REAL.
