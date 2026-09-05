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
echo "===== LOCAL ====="
pwd

echo ""
echo "===== ARQUIVOS ====="
find . -maxdepth 3 -type f -not -path './.git/*' -print | sort

echo ""
echo "===== PASTAS ====="
find . -maxdepth 3 -type d -not -path './.git*' -print | sort

echo ""
echo "===== GIT ====="
git status --short --branch
pwd
echo "=== ARQUIVOS DO PROJETO ==="
find . -maxdepth 2 -type f -print | sort
echo "=== TESTE PRINCIPAL ==="
python -m pytest -q
echo "=== LOCAL ==="
pwd

echo "=== STATUS ==="
git status --short

echo "=== DIFF README ==="
git diff -- README.md

echo "=== ARQUIVOS ==="
find . -maxdepth 2 -type f -print | sort
echo "=== STATUS ==="
git status --short

echo "=== DIFERENÇA DO README ==="
git diff -- README.md

echo "=== CONTEÚDO ATUAL ==="
head -5 README.md

echo "=== VERSÃO DO GITHUB ==="
git show HEAD:README.md | head -5
echo "=== TESTE DO SIGNAL ENGINE ==="
python -m pytest test_signal_engine.py -v
