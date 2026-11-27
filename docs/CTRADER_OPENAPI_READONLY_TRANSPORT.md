# cTrader Open API — transporte DEMO somente leitura

O adaptador de candles existente agora pode usar o transporte oficial Spotware em
`integration/ctrader_openapi_readonly_transport.py`.

## Limites e garantias

- Usa exclusivamente `EndPoints.PROTOBUF_DEMO_HOST`; não existe seletor LIVE.
- Carrega o SDK oficial sob demanda. Sem o pacote, a inicialização falha com
  mensagem explícita, sem simular conexão.
- Um reactor Twisted compartilhado atende os clientes do processo; não inicia
  um reactor por conta e não tenta reiniciá-lo após encerramento.
- Cada instância de transporte representa uma conta e recebe token OAuth e
  credenciais da aplicação por injeção confiável do servidor.
- A lista de contas autorizadas pelo token é consultada no servidor Spotware.
  A conta selecionada precisa ter `isLive == false`; a autenticação da conta
  ocorre somente depois dessa verificação.
- Expõe apenas autenticação de aplicação/conta, leitura de símbolos e leitura
  histórica de trendbars. Não implementa mensagens de ordem, cancelamento,
  alteração de posição ou movimentação financeira.
- Erros de rede são reduzidos a mensagens genéricas para não expor credenciais.

## Instalação opcional

No ambiente de execução que habilitar cTrader, instalar o SDK mantido pela
Spotware:

```bash
python -m pip install ctrader-open-api
```

O pacote não é uma dependência obrigatória do aplicativo inteiro. MT5, TradingView
e os demais módulos não devem depender da presença do SDK cTrader.

## Encadeamento

1. Resolver client ID/secret e access token no backend, nunca no navegador.
2. Criar uma instância por conta com `CTraderOpenApiReadOnlyTransport`.
3. Chamar `connect()`.
4. Usar `CTraderReadOnlyMarketDataAdapter.handshake()`: autenticação da
   aplicação, consulta das contas concedidas pelo OAuth, bloqueio de conta REAL
   e autenticação da conta DEMO.
5. Só depois do handshake verificado, registrar/bindar o adaptador na sessão
   isolada do tenant.
6. Consultar candles pelo adaptador. O adaptador limita chamadas históricas a
   cinco por segundo por conexão.

## O que ainda não está concluído

Este commit entrega o transporte de protocolo e seus limites de segurança, mas
não configura credenciais de aplicação, KMS de produção, worker de renovação,
provisionamento de conta no ambiente hospedado nem conexão real com uma conta
DEMO. Também não habilita streaming de ticks/trendbars; a leitura atual é
histórica/polling e precisa ser validada com uma conta Spotware antes de ser
considerada operacional. Não marcar conta como conectada nem mostrar dados
como atuais sem handshake e heartbeat reais.
