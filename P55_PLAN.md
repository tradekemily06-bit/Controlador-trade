# P55 — Conhecimento confiável

## Objetivo
Criar a fronteira que promove somente uma validação P54 explicitamente VALIDATED para conhecimento confiável, preservando a origem e sem confundir validação com causalidade ou garantia de desempenho futuro.

## Regras
- consumir somente validação P54 válida;
- somente status VALIDATED pode ser promovido;
- preservar hypothesis_id e test_id como proveniência;
- conhecimento não deve afirmar causalidade, certeza ou acurácia futura;
- não alterar estratégia, score, risco ou execução;
- resultado imutável e determinístico;
- entradas inválidas falham fechado.

## Critério de encerramento
Existe uma fronteira explícita entre resultado de validação e conhecimento confiável, mantendo rastreabilidade e impedindo que hipóteses rejeitadas ou inconclusivas contaminem o conhecimento operacional.
