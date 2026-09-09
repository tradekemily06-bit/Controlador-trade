# P7 — Market Data Feed Foundation

## Objetivo
Estabelecer uma fronteira broker-agnóstica para entrada de dados de mercado.

## Garantias
- request explícito com symbol, timeframe e limit;
- normalização antes do núcleo;
- validação de candles vazios, inválidos, fora de ordem ou duplicados;
- aplicação do limite somente após validação;
- nenhum provedor externo nesta etapa;
- nenhuma alteração na estratégia ou na execução REAL.
