# Runbook de provisionamento do relay MT5 (DEMO)

Este runbook configura uma única instância do relay para uma única origem MT5. Ele não conecta uma corretora por meio do navegador e não cria suporte multi-conta automaticamente.

## Relay multi-conta isolado por identidade (novo caminho)

O runtime também oferece a rota por conta:

- `POST /api/bridge/mt5/connections/{connection_id}/candles` recebe candles para uma única conexão.
- O bearer token é resolvido por um serviço de segredos injetado no host. O contrato é `resolve(token) -> (TenantContext, connection_id)`; o resolvedor deve armazenar/verificar hashes de tokens e devolver identidade obtida do cadastro do servidor, nunca de campos enviados pelo cliente.
- `StandaloneRuntime` aceita `tenant_mt5_relay_source_id_resolver(context, connection_id)` e `tenant_mt5_relay_token_resolver`. Sem ambos os serviços reais provisionados pelo host, o fluxo permanece fechado e retorna indisponível.
- A rota exige HTTPS direto ou TLS terminado por proxy explicitamente confiável. O token deve estar vinculado ao mesmo `connection_id` da URL. O tenant, subject, source ID e caminho do banco nunca vêm do payload.
- O registry cria um SQLite separado por tenant/subject/conta, e o store continua impondo DEMO, frescor, UUID anti-replay e validação dos candles.
- Essa rota é somente ingestão de dados; não habilita ordens nem execução REAL.

O endpoint antigo `/api/bridge/mt5/candles` com token global permanece legado para operação local/instância única. Não o use como mecanismo de autenticação multi-conta ou para apresentar contas independentes.

## Provisionamento de uma conta MT5 pelo aplicativo

O backend oferece `POST /api/market-data/mt5-relay-connections` para a identidade autenticada. O corpo aceita somente `account_alias`; o servidor gera `connection_id`, `source_id` e um bearer token aleatório de alta entropia. O token é revelado uma única vez e somente seu SHA-256 é persistido no cofre SQLite local do runtime.

A conexão nasce em `PENDING`. O primeiro lote recebido em `POST /api/bridge/mt5/connections/{connection_id}/candles` precisa passar pelas validações de origem, UUID, timestamp, candles, `account_mode=DEMO` e referência pseudônima derivada do login/servidor do terminal. O backend vincula essa referência à conexão no primeiro handshake e rejeita lotes posteriores se outro login/servidor for usado com o mesmo token. O login bruto não é armazenado. Só após esse primeiro lote válido o backend promove a conta para `CONNECTED`. Qualquer conta em outro modo permanece pendente e sem análise.

A rota `DELETE /api/market-data/connections/{connection_id}` revoga também o token do relay. O token não deve ser copiado para o frontend Lovable nem enviado em logs ou tickets. Se o token de uso único for perdido, revogue a conexão e faça novo provisionamento.

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
- `CONTROLADOR_MT5_RELAY_TOKEN`: token de uso único provisionado para esta conexão.
- `CONTROLADOR_MT5_RELAY_CONNECTION_ID`: ID de 32 caracteres hexadecimais retornado pelo provisionamento da conta. Quando definido, o agente usa `/api/bridge/mt5/connections/{connection_id}/candles`; sem ele, permanece no endpoint legado global.
- `CONTROLADOR_MT5_RELAY_SOURCE_ID`: identificador de origem retornado pelo provisionamento do servidor, exatamente igual ao cadastrado para esta conexão. É obrigatório no modo multi-conta.
- `CONTROLADOR_MT5_TERMINAL_PATH`: caminho opcional do `terminal64.exe` desta instalação MT5. Configure um caminho distinto em cada instância quando operar várias contas/terminais.
- `CONTROLADOR_MT5_SYMBOLS`: lista separada por vírgulas dos símbolos disponíveis na conta.
- `CONTROLADOR_MT5_TIMEFRAMES`: períodos suportados pelo adapter, separados por vírgulas.
- Opcional: `CONTROLADOR_MT5_RELAY_INTERVAL` (padrão 5 segundos) e `CONTROLADOR_MT5_RELAY_CANDLE_LIMIT` (padrão 250, máximo 500).

Inicie o agente com `python -m integration.mt5_local_bridge_agent`. Com `CONNECTION_ID`, token e source ID próprios, ele envia para a rota tenant-scoped da conta; execute uma instância do agente por conta/terminal, cada uma com suas próprias variáveis. Sem `CONNECTION_ID`, ele usa apenas o endpoint legado de instância única. O agente confirma DEMO antes de publicar cada lote. Mantenha o processo local e o terminal MT5 em execução para que novos dados cheguem ao servidor.

## Semântica de tempo dos candles MT5

O campo `rate["time"]` retornado pelo pacote Python MetaTrader 5 representa o horário UTC de abertura da barra, em segundos desde Unix epoch. O adapter converte esse instante diretamente para um `datetime` UTC; não aplica deslocamento local do Windows nem tenta converter o fuso horário visual do servidor da corretora.

Essa regra de timestamp é documentada pela MetaQuotes para `copy_rates_from`, `copy_rates_from_pos` e `copy_rates_range`:
- https://www.mql5.com/pt/docs/python_metatrader5/mt5copyratesfrom_py
- https://www.mql5.com/pt/docs/python_metatrader5/mt5copyratesfrompos_py

**UTC do timestamp não equivale a calendário de sessão confirmado.** O instante UTC informa quando a barra abriu, mas não define sozinho o horário em que o broker encerra cada sessão diária ou semanal, nem feriados, pausas, horário de verão ou reabertura de mercado. Por isso, D1 e W1 continuam bloqueados pelo monitor até que o adapter forneça um calendário de sessão verificável para a conta/provedor. Não derive a próxima validade de D1/W1 somando 24 horas ou 7 dias ao timestamp.

M1, M5 e demais períodos intradiários usam timestamps UTC e seus ciclos próprios. A barra em formação é excluída por `copy_rates_from_pos(..., start_pos=1, ...)`; somente barras fechadas são enviadas para análise.

## Verificação e falhas

1. Consulte `GET /api/bridge/mt5/status` no contexto de operador local.
2. Confirme heartbeat recente e candles recebidos para os símbolos/períodos configurados.
3. Consulte `GET /api/market-data/providers` e confirme que o provider selecionado é `mt5_relay`.
4. Execute análise somente depois de validar símbolo, timeframe, atualidade e completude dos candles.

Se o heartbeat expirar, a conexão cair, o token/TLS falhar, a origem divergir ou os candles forem inválidos/obsoletos, a análise deve permanecer indisponível ou `AGUARDAR`; não substitua dados ausentes por cache apresentado como tempo real.

Para mudar a conta vinculada, faça um provisionamento controlado com banco, token e source ID próprios. Não altere o source ID no agente esperando que o relay troque de conta.

## Próximas etapas necessárias para multi-corretora

Cada integração adicional exige adapter próprio, autenticação/consentimento do usuário, armazenamento de credenciais criptografado, lifecycle tenant/account-scoped, reconexão/revogação, testes de handshake reais e relay isolado. A presença de um provider no registry ou a configuração deste runbook não prova que uma corretora esteja conectada.
