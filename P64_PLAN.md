# P64 — registro controlado de ativação

Objetivo: registrar explicitamente que uma adaptação aprovada foi disponibilizada para um contexto controlado, sem executar ordens e sem alterar automaticamente estratégia, score ou risco.

Regras:
- exige `AppliedAdaptation` válido;
- preserva `proposal_id` e `application_id`;
- exige `activation_id` e `context` explícitos;
- imutável e determinístico;
- fail-closed em entradas inválidas;
- `real_execution_allowed=False`;
- não acessa broker, rede, execução ou memória mutável.
