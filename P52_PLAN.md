# P52 — Contrato de evidência para aprendizado

## Objetivo
Transformar somente registros P51 elegíveis em evidência explícita para pesquisa e aprendizado, preservando a diferença entre fato verificado e hipótese.

## Regras
- consumir somente `VERIFIED` de P51;
- rejeitar `UNVERIFIED` e `MISMATCHED` como evidência confiável;
- preservar ciclo, resultado e valor financeiro já observado;
- marcar a evidência como factual, sem afirmar causalidade ou generalização;
- não alterar estratégia, score, risco ou execução;
- não persistir nem acessar rede;
- resultado imutável e determinístico;
- entradas inválidas falham fechado.

## Critério de encerramento
Existe um contrato que fornece evidência factual para camadas futuras de análise sem permitir que um resultado isolado seja promovido automaticamente a regra de trading.
