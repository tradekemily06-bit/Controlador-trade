# Runbook de provisionamento do relay MT5 (DEMO)

Este runbook configura uma única instância do relay para uma única origem MT5. Ele não conecta uma corretora por meio do navegador e não cria suporte multi-conta automaticamente.

## Limites atuais

- O agente local usa o adapter `ICMarketsMT5DemoMarketDataAdapter`: atualmente, esta implementação concreta é IC Markets MT5 DEMO.
- O agente é outbound-only: envia candles ao servidor por HTTPS. Não exige EA nem porta inbound no computador.
- O relay é somente leitura e aceita exclusivamente `account_mode=DEMO`.
- Cada banco de relay é provisionado para um único `CONTROLADOR_MT5_RELAY_SOURCE_ID`. Uma origem diferente é rejeitada.
- O identificador de origem é uma allowlist operacional, não autenticação. O token bearer dedicado e TLS continuam obrigatórios.
- O relay não fornece OAuth, cofre de credenciais, conexão genérica com qualquer corretora, nem várias contas simultâneas.
- Nenhuma rota deste fluxo envia ordens ou movimenta dinheiro; execução REAL continua desabilitada.

## Configuração no servidor

Configure no ambiente do servidor, nunca no JavaScript do navegador:

- `CONTROLADOR_MARKET_DATA_PROVIDER=mt5_relay` (ou inclua `mt5_relay` na lista explicitamente configurada).
- `CONTROLADOR_MT5_RELAY_TOKEN`: segredo aleatório forte, diferente de qualquer token de usuário.
- `CONTROLADOR_MT5_RELAY_SOURCE_ID`: identificador fixo para esta origem, por exemplo `mt5-local-main`.
- `CONTROLADOR_RUNTIME_DIR`: diretório persistente e gravável para o banco `mt5-relay.sqlite3`.

Não reutilize o mesmo token, banco ou source ID entre contas. Proteja os segredos pelo gerenciador de segredos do ambiente de hospedagem. Exija HTTPS; se TLS terminar em proxy, habilite `CONTROLADOR_TRUST_PROXY_TLS` somente quando o proxy confiável sobrescrever o cabeçalho de protocolo encaminhado.

## Configuração no computador com MT5

Instale as dependências compatíveis com o terminal MetaTrader 5 e configure no ambiente do agente local:

- `CONTROLADOR_MT5_RELAY_URL`: URL HTTPS base do aplicativo hospedado.
- `CONTROLADOR_MT5_RELAY_TOKEN`: o mesmo segredo provisionado no servidor.
- `CONTROLADOR_MT5_RELAY_SOURCE_ID`: exatamente o mesmo identificador fixo provisionado no servidor.
- `CONTROLADOR_MT5_SYMBOLS`: lista separada por vírgulas dos símbolos disponíveis na conta.
- `CONTROLADOR_MT5_TIMEFRAMES`: períodos suportados pelo adapter, separados por vírgulas.
- Opcional: `CONTROLADOR_MT5_RELAY_INTERVAL` (padrão 5 segundos) e `CONTROLADOR_MT5_RELAY_CANDLE_LIMIT` (padrão 250, máximo 500).

Inicie o agente com `python -m integration.mt5_local_bridge_agent`. Ele confirma DEMO antes de publicar cada lote. Mantenha o processo local e o terminal MT5 em execução para que novos dados cheguem ao servidor.

## Verificação e falhas

1. Consulte `GET /api/bridge/mt5/status` no contexto de operador local.
2. Confirme heartbeat recente e candles recebidos para os símbolos/períodos configurados.
3. Consulte `GET /api/market-data/providers` e confirme que o provider selecionado é `mt5_relay`.
4. Execute análise somente depois de validar símbolo, timeframe, atualidade e completude dos candles.

Se o heartbeat expirar, a conexão cair, o token/TLS falhar, a origem divergir ou os candles forem inválidos/obsoletos, a análise deve permanecer indisponível ou `AGUARDAR`; não substitua dados ausentes por cache apresentado como tempo real.

Para mudar a conta vinculada, faça um provisionamento controlado com banco, token e source ID próprios. Não altere o source ID no agente esperando que o relay troque de conta.

## Próximas etapas necessárias para multi-corretora

Cada integração adicional exige adapter próprio, autenticação/consentimento do usuário, armazenamento de credenciais criptografado, lifecycle tenant/account-scoped, reconexão/revogação, testes de handshake reais e relay isolado. A presença de um provider no registry ou a configuração deste runbook não prova que uma corretora esteja conectada.
