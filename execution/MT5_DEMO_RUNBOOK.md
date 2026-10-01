# Runbook — primeira conexão IC Markets MT5 DEMO

Este runbook é para a primeira validação operacional. Nenhuma etapa aqui autoriza REAL.

## Pré-requisitos

1. Windows com o terminal MetaTrader 5 instalado.
2. Conta IC Markets DEMO válida e conectada no terminal.
3. Python no mesmo ambiente compatível com o terminal e o pacote `MetaTrader5` instalado a partir de `requirements-mt5.txt`.
4. Nenhuma credencial salva no GitHub, código-fonte ou logs versionados.
5. Não deve existir posição anterior do Controlador com o mesmo `magic` no símbolo da validação.

## Validação física única

Para evitar tocar em uma posição antiga, a validação usa `execution/mt5_demo_physical_validation.py`. Ela só continua se não houver posição anterior do Controlador no símbolo.

Execute no mesmo Windows em que o terminal MT5 DEMO está conectado:

```text
python execution/mt5_demo_physical_validation.py
```

A sequência executada pelo script é:

1. inicializar o terminal;
2. confirmar conta DEMO;
3. selecionar EURUSD e validar cotação;
4. obter o volume mínimo e o `volume_step` diretamente do MT5;
5. bloquear se já existir posição do Controlador;
6. executar `order_check()` da abertura;
7. executar `order_send()` da abertura;
8. localizar exatamente a posição criada pelo Controlador;
9. guardar o ticket dessa posição;
10. executar `order_check()` do fechamento;
11. executar `order_send()` do fechamento usando o ticket exato;
12. confirmar que nenhuma posição do Controlador permaneceu aberta;
13. imprimir os identificadores e horários necessários para compor a evidência.

O script nunca aceita conta REAL e não salva credenciais.

## Critério de conclusão

A validação física só é considerada **CONCLUÍDA** quando a execução real do script retornar:

```text
VALIDATION=PASSED
DEMO_ONLY=True
REAL=False
REMAINING_CONTROLADOR_POSITIONS=0
```

Além disso, os resultados de abertura e fechamento devem conter confirmação do MT5 e identificadores externos.

Um teste unitário, mock, CI, documentação ou simulação **não substitui** essa evidência.

## Parar imediatamente se

- a conta não for DEMO;
- o símbolo ou preço não estiver disponível;
- já existir posição do Controlador antes do teste;
- `order_check()` rejeitar a abertura ou o fechamento;
- `order_send()` não retornar confirmação válida;
- a posição criada não puder ser identificada de forma única;
- a posição continuar aberta depois do fechamento;
- houver divergência entre MT5 e o estado local;
- houver tentativa de REAL ou AGUARDAR chegar ao adapter.

## O que esta etapa não faz

- não envia ordens reais;
- não transforma `duration_seconds` em expiração binária;
- não substitui o motor de decisão, risco, auditoria ou gateway;
- não exige cTrader para funcionar;
- não considera uma execução simulada como validação física.

A primeira conexão real do ecossistema com MT5 só pode ser comprovada quando o runtime Windows + terminal MT5 + conta IC Markets DEMO estiverem disponíveis.
