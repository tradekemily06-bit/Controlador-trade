# P51 — Fronteira de ingestão para aprendizado

## Objetivo
Preparar a entrada de snapshots factuais P50 para o sistema de aprendizado sem permitir que dados não verificados sejam tratados como conhecimento confiável.

## Regras
- consumir somente snapshot P50 válido;
- preservar origem, ciclo, resultado e reconciliação;
- distinguir `VERIFIED`, `UNVERIFIED` e `MISMATCHED`;
- somente fatos reconciliados podem ser elegíveis a conhecimento confiável;
- não alterar estratégia, score, risco ou execução;
- não persistir nem acessar rede;
- resultado imutável e determinístico;
- entradas inválidas falham fechado.

## Critério de encerramento
Existe uma fronteira que separa ingestão factual de conhecimento confiável, evitando que resultados não verificados contaminem o aprendizado futuro.
