# P65 — observação factual pós-ativação

Objetivo: registrar observações fornecidas explicitamente após a ativação controlada, sem inferir eficácia, causalidade ou desempenho.

Regras:
- exige `AdaptationActivation` válido;
- exige `observation_id` e observação não vazia;
- amostra deve ser inteiro positivo;
- preserva toda a proveniência da ativação;
- imutável, determinístico e fail-closed;
- não promove conhecimento nem altera estratégia, score, risco ou execução.
