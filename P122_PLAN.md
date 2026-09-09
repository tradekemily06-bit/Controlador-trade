# P122 — Contrato de dados de mercado da corretora

## Objetivo
Fechar a fronteira broker-agnostic para receber dados de mercado de uma corretora sem permitir que detalhes de API, autenticação ou transporte entrem no núcleo.

## Contrato
- solicita `symbol`, `timeframe` e `limit` explicitamente;
- o adapter/provider é responsável apenas por obter dados externos;
- o núcleo recebe apenas `Candle` normalizado e validado;
- dados vazios, inválidos, fora de ordem, duplicados, futuros, incompletos ou além do limite são rejeitados;
- o resultado identifica a fonte e o instante de recebimento;
- nenhum dado de mercado dispara execução;
- nenhum dado externo ativa REAL;
- não há chamadas de rede neste núcleo.

## Segurança
A fronteira falha fechada. A integração concreta com uma corretora será feita posteriormente em adapter próprio, depois de P122.
