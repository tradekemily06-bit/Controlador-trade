# Runbook — IC Markets MT5 DEMO

Este documento descreve a única validação externa que não pode ser simulada pelo Codespace: executar o terminal MetaTrader 5 em um ambiente compatível e confirmar uma conta DEMO.

## Pré-requisitos

- terminal MetaTrader 5 instalado e conectado;
- conta IC Markets DEMO válida;
- Python e o pacote `MetaTrader5` instalados no mesmo runtime suportado pelo terminal;
- nenhum segredo armazenado no repositório.

## Ordem de validação

1. Inicializar o terminal/runtime.
2. Confirmar que `account_info()` retorna uma conta e que o modo é DEMO.
3. Confirmar o símbolo escolhido e sua cotação.
4. Usar uma solicitação de volume explicitamente definido em lotes MT5.
5. Executar `order_check()`.
6. Somente se a checagem for aprovada, executar `order_send()`.
7. Registrar o identificador externo retornado.
8. Consultar o estado externo e reconciliar com o ledger do Controlador Trading.
9. Encerrar a posição por uma operação explícita de fechamento; não usar `duration_seconds` como expiração binária.
10. Confirmar novamente o estado externo e o estado interno.

## Critérios de parada

Interromper imediatamente se:

- a conta não for identificada como DEMO;
- o símbolo/cotação não estiver disponível;
- `order_check()` rejeitar a solicitação;
- `order_send()` retornar rejeição ou ausência de confirmação;
- houver divergência não explicada entre estado externo e ledger;
- houver tentativa de executar `REAL` ou `AGUARDAR`.

## Regra de segurança

Este runbook não autoriza operações com dinheiro real. A passagem para `REAL` exige uma decisão de segurança separada e não faz parte desta etapa.
