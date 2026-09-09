# P38 — Qualidade de sinal contextual

## Objetivo
Criar uma fronteira determinística que combine a qualidade de sinal já existente com o contexto de mercado validado pelo P37, sem transformar notícias em direção automática.

## Regras
- consumir somente `SignalQuality` e `MarketContextSnapshot` válidos;
- preservar a qualidade base e explicitar o impacto factual do contexto;
- não inferir sentimento, direção ou probabilidade a partir de notícias;
- contexto ausente ou vazio não inventa informação;
- resultado imutável e determinístico;
- entradas inválidas falham fechando;
- nenhuma chamada de rede, corretora ou execução;
- não alterar o `DecisionEngine` existente nesta etapa.

## Critério de encerramento
Existe uma fronteira testada que produz uma avaliação contextual por símbolo, preservando a qualidade original e expondo apenas fatos declarados pelo contexto.
