# Checklist operacional — Controlador Trading

## Antes da conexão

- [x] Núcleo de decisão separado da execução
- [x] COMPRA/VENDA/AGUARDAR definido
- [x] Replay usando o mesmo núcleo
- [x] Memória e estatísticas integradas
- [x] Risk Gate fail-closed
- [x] Notícias sem dados fictícios
- [x] REAL bloqueado
- [x] IC Markets MT5 DEMO isolado como adapter

## Validação MT5 DEMO

- [ ] Terminal MetaTrader 5 compatível disponível no runtime Python
- [ ] `initialize()` com sucesso
- [ ] `account_info()` confirma conta DEMO
- [ ] símbolo selecionado e cotação disponível
- [ ] volume validado em lotes
- [ ] `order_check()` aprovado
- [ ] uma única ordem DEMO controlada enviada
- [ ] ticket/order/deal confirmado
- [ ] posição DEMO fechada
- [ ] resultado reconciliado
- [ ] logs/auditoria confirmados

## Regra

Se qualquer etapa obrigatória falhar ou ficar ambígua, a execução deve permanecer bloqueada. Nenhuma etapa deve ser simulada como se tivesse ocorrido.
