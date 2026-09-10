# Controlador Trading

Sistema de análise, decisão, risco, execução e auditoria.

## Arquitetura

O núcleo de decisão é independente de corretora/plataforma.

Fluxo:

dados → análise → score/filtros → COMPRA/VENDA/AGUARDAR → risco → execução → auditoria

## Ambientes

- DEMO: ambiente de desenvolvimento e validação
- REAL: camada controlada e separada, condicionada à validação e reconciliação da execução externa

## Estrutura

- `core/` — cérebro do sistema
- `data/` — entrada e normalização de dados
- `execution/` — contratos, gateway e adaptadores de execução
- `audit/` — registros e auditoria
- `config/` — configurações
- `analysis/` — análise e validação

## Segurança de execução

O gateway mantém kill switch, idempotência, estados explícitos de execução e tratamento fail-closed para situações ambíguas.

Nenhuma senha, token, refresh token ou client secret de corretora deve ser persistido no repositório.

## Integração DEMO

A integração cTrader DEMO está preparada por boundaries independentes do núcleo. A camada específica da IC Markets permanece bloqueada enquanto a aplicação cTrader Open API estiver pendente de aprovação.

## Estado do projeto

O projeto está em fase de encerramento técnico. Não são criadas novas etapas apenas para prolongar o desenvolvimento. A validação automatizada final deve ser executada no ambiente de execução do projeto; depois dela, ficam apenas a dependência externa da Open API e correções de defeitos reais encontrados no uso DEMO.

Consulte `PROJECT_COMPLETION_STATUS.md` para o estado de conclusão e as pendências externas.
