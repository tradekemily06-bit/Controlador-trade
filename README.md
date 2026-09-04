# Controlador Trading

Sistema de análise, decisão, risco, execução e auditoria de operações.

## Arquitetura

O núcleo de decisão é independente de corretora/plataforma.

Fluxo:
dados → análise → score/filtros → COMPRA/VENDA/AGUARDAR → risco → execução → auditoria

## Ambientes

- DEMO: primeiro ambiente de testes
- REAL: ambiente posterior, usando a mesma lógica do núcleo

## Estrutura

- `core/` — cérebro do sistema
- `data/` — entrada e normalização de dados
- `execution/` — adaptadores de execução
- `audit/` — registros e auditoria
- `config/` — configurações

> Esta versão é a fundação arquitetural. A lógica de entrada será construída e validada por etapas.
