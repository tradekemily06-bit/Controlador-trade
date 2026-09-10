# Gate final antes da conexão com o mercado

O projeto só deve sair da simulação quando a validação operacional externa for possível.

## Permitido

- leitura do estado do terminal;
- confirmação de conta DEMO;
- leitura de símbolo/cotação;
- `order_check()`;
- ordem de teste exclusivamente DEMO, com fechamento e reconciliação.

## Bloqueado

- credenciais no código ou Git;
- envio quando a conta não for confirmada como DEMO;
- `AGUARDAR` como ordem;
- bypass do Risk Gate;
- execução REAL;
- tratar resposta ambígua como sucesso.

O Android pode ser usado para acompanhar a conta IC Markets DEMO, mas a ponte Python depende de um terminal MetaTrader 5 compatível.
