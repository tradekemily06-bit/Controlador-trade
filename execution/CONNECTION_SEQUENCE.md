# Sequência de conexão — IC Markets MT5 DEMO

## Pré-condições

- conta IC Markets DEMO criada;
- terminal MetaTrader 5 compatível instalado e conectado;
- credenciais mantidas somente no ambiente do terminal/runtime;
- nenhum segredo no Git.

## Execução controlada

1. Inicializar o terminal via integração Python.
2. Confirmar `account_info()` e modo DEMO.
3. Confirmar símbolo e `symbol_info_tick()`.
4. Validar volume e parâmetros do símbolo.
5. Executar `order_check()`.
6. Somente se aprovado, executar uma ordem DEMO controlada.
7. Registrar ticket/deal externo.
8. Fechar a posição DEMO de teste.
9. Reconciliar estado local e externo.
10. Encerrar o teste se qualquer etapa for ambígua.

A existência deste documento não habilita execução automática nem REAL.
