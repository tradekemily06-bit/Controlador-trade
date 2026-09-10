# IC Markets cTrader DEMO — integração preparada

A conta IC Markets cTrader DEMO já pode ser representada pelo núcleo por meio de `ICMarketsDemoConfig`, sem gravar senha, token ou client secret no repositório.

## Estado atual

- A camada de execução continua broker-agnostic.
- A configuração aceita somente `DEMO`.
- A conta é identificada por `account_id` e servidor, sem credenciais persistidas.
- Enquanto a aplicação cTrader Open API não estiver aprovada, a boundary permanece `API_PENDING_APPROVAL` e recusa qualquer envio.
- Nenhuma chamada de rede é feita por esta camada de preparação.

## Quando a API estiver aprovada

A implementação de transporte poderá ser conectada atrás desta boundary. O gateway, os contratos de execução, o kill switch, a idempotência e a auditoria não precisam ser refeitos.

## Segurança

Nunca colocar senha da conta, access token, refresh token ou client secret em código, commits, README ou testes. Esses valores devem entrar somente por um mecanismo externo de segredo/configuração em runtime.
