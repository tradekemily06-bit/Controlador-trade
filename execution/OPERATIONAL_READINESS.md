# Controlador Trading — prontidão operacional

## Objetivo

Registrar o último gate interno antes da conexão do ecossistema com o mercado financeiro via IC Markets MT5 DEMO.

## Gates obrigatórios

1. Núcleo de decisão permanece broker-agnóstico.
2. `COMPRA`, `VENDA` e `AGUARDAR` continuam explícitos.
3. Risk Gate permanece fail-closed.
4. Gateway de execução não recebe `AGUARDAR`.
5. Adapter IC Markets aceita somente `DEMO`.
6. `order_check()` ocorre antes de `order_send()`.
7. Nenhum segredo é persistido no repositório.
8. REAL permanece desabilitado.
9. A conexão operacional deve confirmar conta DEMO antes de qualquer ordem.
10. Uma ordem DEMO controlada só pode ser enviada após preflight e reconciliação das respostas.

## Sequência operacional

`terminal MT5 compatível → preflight → conta DEMO → símbolo/cotação → validação de volume → order_check → ordem DEMO controlada → confirmação → fechamento → reconciliação`

## Limite atual

O aplicativo MT5 para Android não fornece, por si só, o terminal local necessário para a integração Python `MetaTrader5`. Portanto, a conexão final exige um ambiente compatível com o terminal MetaTrader 5 (por exemplo, Windows ou uma VM/VPS Windows).

Até essa validação, o sistema deve permanecer em SIMULAÇÃO e nenhuma ordem deve ser enviada automaticamente.
