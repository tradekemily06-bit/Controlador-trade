# P23 — Market Data Integrity

## Objetivo
Adicionar uma fronteira somente leitura para avaliar frescor, continuidade e ordem dos candles antes do uso operacional.

## Regras
- dados vazios ou candles inválidos => INVALID;
- timestamps fora de ordem ou duplicados => INVALID;
- intervalo esperado com lacunas => GAP;
- último candle além da idade máxima => STALE;
- dados válidos e atuais => HEALTHY;
- nenhuma execução, estratégia ou conexão com corretora é alterada.
