# Controlador Trading

Sistema de análise, decisão, risco, execução e auditoria.

## Arquitetura

O núcleo de decisão é independente de corretora/plataforma.

Fluxo:

dados → análise → score/filtros → COMPRA/VENDA/AGUARDAR → risco → execução → auditoria

## Ambientes

- DEMO: ambiente de desenvolvimento e validação
- REAL: camada controlada e separada, bloqueada até validação operacional e reconciliação suficientes

## Estrutura

- `core/` — cérebro do sistema
- `data/` — entrada e normalização de dados
- `execution/` — contratos, gateway e adaptadores de execução
- `audit/` — registros e auditoria
- `config/` — configurações
- `analysis/` — análise e validação
- `integration/` — orquestração do ecossistema, notícias e integrações
- `web/` — shell mobile-first

## Segurança de execução

O gateway mantém kill switch, idempotência, estados explícitos de execução e tratamento fail-closed para situações ambíguas.

Nenhuma senha, token, refresh token ou client secret de corretora deve ser persistido no repositório.

## Ecossistema

O shell mobile-first já expõe Painel, Análise, Replay, Memória, Estatísticas, Risco, Notícias e Conexões por APIs internas. A execução permanece bloqueada por padrão.

O estado operacional consolidado está em `OPERATIONAL_READINESS.md`.

## Integração DEMO

A primeira integração operacional escolhida é **IC Markets MT5 DEMO**. O adapter, o preflight somente leitura, os testes de segurança e o runbook já estão no projeto.

A integração cTrader DEMO permanece isolada como futura alternativa e não bloqueia o caminho MT5.

A validação de execução Python contra uma conta IC Markets DEMO ainda requer um terminal MetaTrader 5 compatível com o pacote oficial `MetaTrader5`. O MT5 Android não substitui esse terminal para a comunicação Python.

## Estado do projeto

A parte de software necessária para a integração IC Markets MT5 DEMO está em encerramento técnico. A próxima validação operacional é: terminal MT5 compatível → preflight → símbolo/cotação → `order_check()` → ordem DEMO controlada → confirmação → fechamento → reconciliação.

Consulte `PROJECT_COMPLETION_STATUS.md`, `OPERATIONAL_READINESS.md` e `execution/MT5_DEMO_RUNBOOK.md` para os critérios e a sequência operacional.
