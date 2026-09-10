# P128 — cTrader DEMO OAuth/session boundary

## Objetivo

Preparar a autenticação do Controlador Trading com o cTrader Open API para a conta DEMO sem colocar `client_secret`, access token ou refresh token no núcleo ou no repositório.

## Fluxo

1. A aplicação cTrader deve estar aprovada/ativa.
2. O usuário autoriza o aplicativo via OAuth 2.0 com `scope=trading`.
3. O callback recebe o código de autorização.
4. Uma camada externa troca o código por access/refresh tokens.
5. A sessão DEMO expõe somente metadados necessários ao núcleo.
6. Somente `AUTHENTICATED` pode ser considerado utilizável.

## Segurança

- Nenhum segredo é armazenado neste módulo.
- O `client_secret` nunca entra na URL de autorização.
- Tokens ficam sob responsabilidade da camada externa de credenciais.
- O módulo não faz chamadas de rede.
- A conexão de mercado permanece DEMO: `demo.ctraderapi.com:5035`.
- REAL não é habilitado por este passo.

## Estado atual

O aplicativo `Controlador Trading` precisa estar `Active` antes do fluxo OAuth de trading poder ser concluído. Enquanto estiver `Submitted`, o código apenas prepara a fronteira; não deve tentar contornar a revisão da Spotware.
