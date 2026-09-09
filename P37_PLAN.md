# P37 — Agregação determinística de contexto de mercado

## Objetivo
Transformar eventos já validados pelo P36 em um snapshot imutável e determinístico de contexto por símbolo, sem inferir sentimento, gerar sinais ou autorizar execução.

## Regras
- consumir somente `NewsEvent` válidos do P36;
- permitir agregação por símbolo sobre um conjunto de eventos já validado;
- preservar a contagem total e a distribuição explícita de impacto;
- manter eventos ordenados deterministicamente;
- rejeitar entradas inválidas e símbolos vazios;
- não inferir sentimento, direção ou probabilidade de preço;
- não alterar estratégia, risco, alertas ou execução;
- nenhuma chamada de rede ou corretora;
- resultado imutável e seguro para consumo posterior;
- contexto vazio é válido quando não há eventos relevantes.

## Critério de encerramento
Existe uma fronteira testada que produz um snapshot determinístico de notícias por símbolo a partir do contrato P36, preservando apenas fatos declarados e sem transformar notícias em decisão de trading.

## Próxima etapa
Uma etapa posterior poderá conectar provedores concretos ou consumir o snapshot em análises de contexto, sem permitir que esta camada execute ordens ou altere o estado operacional.