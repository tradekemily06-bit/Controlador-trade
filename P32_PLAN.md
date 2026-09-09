# P32 — Unificação do fluxo DEMO com a fronteira de prontidão

## Objetivo
Remover o caminho legado em que `DemoFlow` chama `PaperExecutor` diretamente e fazer o fluxo DEMO passar pela cadeia P30 → P31 → `ExecutionGateway`.

## Regras
- análise e decisão continuam separadas da execução;
- `DemoFlow` cria uma `ExecutionIntent` somente após `FinalDecision.EXECUTAR`;
- a intenção é sempre DEMO e nunca REAL;
- prontidão P30 deve ser verificada antes do gateway;
- o `ExecutionGateway` permanece como única fronteira de execução;
- kill switch, integridade de mercado, recuperação e configuração inválida devem bloquear antes do executor;
- não introduzir replay, retry automático ou chamadas diretas a corretoras;
- preservar auditoria da análise, decisão e resultado de execução;
- manter testes de regressão para AGUARDAR, estado operacional ausente e contexto desfavorável.

## Critério de encerramento
`DemoFlow` não possui mais caminho de execução DEMO que contorne P30/P31. O fluxo aprovado cria uma intenção válida e chega ao gateway; qualquer bloqueio de prontidão impede a chamada ao executor.
