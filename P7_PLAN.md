# P7 — Market Data Feed Foundation

## Objetivo
Estabelecer uma fronteira broker-agnóstica para entrada de dados de mercado, mantendo o núcleo de decisão independente do provedor.

## Escopo concluído
- [x] request explícito com `symbol`, `timeframe` e `limit`;
- [x] contrato `MarketDataProvider` sem dependência de broker;
- [x] normalização dos candles antes da entrada no núcleo;
- [x] rejeição de resposta vazia;
- [x] validação de candles inválidos;
- [x] rejeição de candles fora de ordem;
- [x] rejeição de timestamps duplicados;
- [x] aplicação do `limit` somente depois da validação;
- [x] resultado imutável com candles, fonte e timestamp de recebimento;
- [x] exportação pública do contrato em `data.__init__`;
- [x] testes automatizados da fronteira de segurança;
- [x] nenhum provedor externo acoplado nesta etapa;
- [x] nenhuma alteração na estratégia ou na execução REAL.

## Critério de encerramento
P7 é considerado concluído quando a camada `MarketDataFeed` aceitar somente dados normalizados e validados, limitar a série após a validação e permanecer independente de qualquer broker/exchange específico.

## Próxima etapa
Não adicionar integração com broker nesta fase. O próximo trabalho do roadmap pode consumir este contrato sem alterar a fronteira de dados.
