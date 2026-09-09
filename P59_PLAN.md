# P59 — Replay e teste controlado de conhecimento

## Objetivo
Permitir que conhecimento auditado seja estudado em laboratório/replay sem modificar silenciosamente o estado operacional.

## Regras
- consumir somente conhecimento aprovado pela fronteira P58;
- identificar explicitamente o cenário/lab;
- produzir somente resultado de estudo, sem execução de mercado;
- não promover automaticamente resultado experimental a conhecimento confiável;
- não alterar estratégia, score, risco ou execução;
- preservar rastreabilidade;
- imutável, determinístico e fail-closed.

## Critério de encerramento
O conhecimento pode ser submetido a replay/laboratório de forma isolada, mantendo separação entre experimento e operação.
