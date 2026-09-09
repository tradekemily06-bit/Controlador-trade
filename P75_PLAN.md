# P75 — validação do handoff

Valida o handoff P74 antes de permitir que o contexto seja consumido por uma futura etapa.

Regras: handoff válido, IDs/proveniência completos, estado explícito `VERIFIED` ou `BLOCKED`, fail-closed, sem inferência de eficácia/causalidade/lucro e sem mutação de estratégia, score, risco ou execução REAL.
