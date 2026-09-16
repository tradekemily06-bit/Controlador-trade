# Auditoria profunda — política de limites, escala e capacidade

## Objetivo

Esta política separa **limite funcional do produto** de **proteção de recursos** e de **regra legítima de risco**. O ecossistema não deve inventar um teto de funcionalidade apenas para simplificar implementação ou encerrar uma auditoria.

## 1. Proibido como limite funcional

Não usar números fixos para limitar artificialmente:

- quantidade de cenários de replay/backtest/laboratório;
- quantidade de análises que o usuário pode solicitar por característica do produto;
- quantidade de instrumentos, mercados ou módulos suportados;
- profundidade de conhecimento/currículo do Senior/Professor;
- quantidade de evidências ou fontes que podem compor uma competência;
- histórico do usuário como capacidade funcional;
- evolução futura do ecossistema;
- quantidade de estratégias, estudos ou registros por plano comercial.

O produto deve crescer por arquitetura de dados, paginação, streaming, processamento assíncrono, filas e armazenamento adequado, e não por um teto funcional arbitrário.

## 2. Proteções legítimas de recursos

Podem existir limites técnicos quando o objetivo é impedir exaustão de recursos ou abuso. Exemplos já existentes:

- tamanho máximo de payload HTTP;
- rate limit por janela;
- retenção local de eventos de segurança;
- tamanho máximo de mídia enviada;
- timeout/cancelamento;
- concorrência e backpressure;
- paginação e tamanho de lote definido pela infraestrutura;
- limites físicos do armazenamento, CPU ou memória da implantação.

Esses mecanismos devem ser classificados como **infraestrutura/anti-abuso**, não como capacidade do produto. Sempre que possível, a API deve oferecer cursor, streaming, processamento assíncrono ou continuação em vez de transformar o limite de uma página/resposta em teto do conjunto de dados.

## 3. Regras legítimas de risco

Limites como perda diária máxima, exposição máxima, margem, tamanho máximo de ordem, concentração e kill switch são regras de segurança financeira. Eles não são limites arbitrários de funcionalidade e não devem ser removidos apenas por causa da política de capacidade.

Eles precisam ser explícitos, configuráveis conforme o contexto, auditáveis e independentes da camada de conhecimento.

## 4. Casos que exigem revisão arquitetural

### Decision history

Contratos de produção que atualmente recebem `limit=100` devem evoluir para leitura paginada/cursorizada ou streaming. O valor de uma página não pode significar que o histórico funcional termina naquele número.

### Replay

O núcleo não possui teto artificial de quantidade de cenários. A proteção deve considerar custo real: payload, memória, CPU, duração, concorrência, armazenamento, cancelamento, recuperação e tamanho da resposta. A execução continua bloqueada.

### Security audit

A retenção local limitada é um cache de segurança/recurso. Em produção multi-réplica, a fonte de verdade deve ser compartilhada e durável; o limite local não pode ser apresentado como retenção total do sistema.

### Rate limiting

O limite local é proteção por processo. Em produção com múltiplas réplicas, a autoridade precisa ser compartilhada/centralizada para evitar inconsistência entre réplicas.

### Trading runtime

`max_cycles` é quantidade solicitada para uma execução específica, não um teto global do produto. A documentação e os testes devem preservar essa distinção.

## 5. Regra de decisão

Antes de adicionar ou manter qualquer `MAX_*`, `limit`, `quota`, `count` ou valor padrão relacionado a capacidade, classificar o mecanismo em uma destas categorias:

1. **Produto** → não pode impor teto funcional artificial.
2. **Infraestrutura/anti-abuso** → pode existir se protege recurso real e possui comportamento de continuação/escala quando aplicável.
3. **Risco/segurança financeira** → pode existir e deve ser auditável.
4. **Frescura/validade temporal** → pode existir quando representa validade dos dados, não capacidade.
5. **Observabilidade/retention local** → pode existir como cache/buffer, mas não pode ser confundido com retenção durável total.

A classificação deve ser registrada na documentação e, quando o mecanismo for relevante para produção, coberta por testes.
