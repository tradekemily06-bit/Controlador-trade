# Controlador Trading — Operational Readiness

## Estado atual

- Decision Core: ONLINE
- Análise: ONLINE
- Replay: ONLINE
- Memória: ONLINE na sessão atual
- Estatísticas: ONLINE na sessão atual
- Risk Gate: FAIL-CLOSED quando o estado operacional não está disponível
- Notícias: OFFLINE até um provedor real ser configurado
- Execution Gateway: ONLINE como boundary interno
- IC Markets MT5 DEMO: validação operacional pendente
- REAL: DESABILITADO

## Regra de segurança

Nenhuma camada da interface deve transformar ausência de estado operacional, ausência de provedor de notícias ou ausência de terminal MT5 compatível em autorização de execução.

## Próximo marco operacional

Validar a ponte Python → terminal MetaTrader 5 compatível → conta IC Markets DEMO. Essa validação deve ser somente DEMO, começar por health/read-only, confirmar conta e símbolo, executar `order_check`, e só então permitir uma ordem DEMO controlada. O resultado deve ser reconciliado por identificador externo e a posição DEMO deve ser encerrada após o teste.

O aplicativo Android do MT5, sozinho, não é considerado uma ponte Python para o runtime do projeto.
