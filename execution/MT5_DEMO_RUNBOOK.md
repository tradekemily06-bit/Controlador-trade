# Runbook — primeira conexão IC Markets MT5 DEMO

Este runbook é para a primeira validação operacional. Nenhuma etapa aqui autoriza REAL.

## Pré-requisitos

1. Windows com o terminal MetaTrader 5 instalado.
2. Conta IC Markets DEMO válida e conectada no terminal.
3. Python no mesmo ambiente compatível com o terminal e o pacote `MetaTrader5` instalado a partir de `requirements-mt5.txt`.
4. Nenhuma credencial salva no GitHub, código-fonte ou logs versionados.

## Ordem segura da validação

1. Inicializar o terminal MT5.
2. Executar o preflight `check_mt5_demo_health()`.
3. Confirmar que a conta retornada é DEMO.
4. Confirmar o símbolo escolhido e a cotação disponível.
5. Usar volume explícito em **lotes**, respeitando o mínimo/step do símbolo.
6. Montar a requisição de mercado.
7. Executar `order_check()`.
8. Somente se a checagem for aprovada, executar `order_send()`.
9. Registrar o identificador externo retornado pelo MT5.
10. Reconciliar o resultado com o estado local/auditoria.
11. Fechar explicitamente a posição DEMO em uma etapa controlada.
12. Reconciliar novamente após o fechamento.

## Parar imediatamente se

- a conta não for DEMO;
- o símbolo ou preço não estiver disponível;
- `order_check()` rejeitar a requisição;
- `order_send()` não retornar confirmação válida;
- houver divergência entre MT5 e o estado local;
- houver tentativa de `REAL` ou `AGUARDAR` chegar ao adapter.

## O que esta etapa não faz

- não envia ordens reais;
- não transforma `duration_seconds` em expiração binária;
- não substitui o motor de decisão, risco, auditoria ou gateway;
- não exige cTrader para funcionar.

A primeira conexão real do ecossistema com MT5 só pode ser comprovada quando o runtime Windows + terminal MT5 + conta IC Markets DEMO estiverem disponíveis.
