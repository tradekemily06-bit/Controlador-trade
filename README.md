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
- `integration/` — orquestração do ecossistema
- `web/` — interface responsiva para celular e notebook

## Segurança de execução

O gateway mantém kill switch, idempotência, estados explícitos de execução e tratamento fail-closed para situações ambíguas.

Nenhuma senha, token, refresh token ou client secret de corretora deve ser persistido no repositório.

## Integração DEMO

A primeira integração operacional escolhida é **IC Markets MT5 DEMO**. O adapter, o preflight somente leitura, os testes de segurança, o runbook e o fluxo controlado de primeira ordem já estão no projeto.

A validação operacional DEMO já foi concluída: uma ordem controlada de EURUSD 0,01 lote em COMPRA foi confirmada no IC Markets MT5 DEMO e posteriormente fechada pelo fluxo controlado. O identificador externo e o fechamento foram tratados pela camada de execução.

A integração cTrader DEMO permanece isolada como futura alternativa e não bloqueia o caminho MT5.

## Interface do ecossistema

A interface web responsiva já integra Painel, Análise, Replay, Memória, Estatísticas, Risco, Notícias/Contexto e Conexões. O manifest web é servido pelo próprio aplicativo e os endpoints possuem contratos automatizados. A interface permanece em SIMULAÇÃO e não autoriza execução REAL.

Para validação local, execute `python app.py` em um ambiente Python compatível e abra o endereço exibido pelo servidor. A validação visual em celular/notebook continua sendo uma verificação de uso da interface, não uma autorização de execução financeira.

## Estado do projeto

O software necessário para o núcleo, as fronteiras de execução DEMO, a integração IC Markets MT5 DEMO e a interface responsiva está implementado e coberto pela suíte de testes/CI. REAL permanece bloqueado.

Novos trabalhos devem ser motivados por uma necessidade concreta, defeito encontrado na validação ou expansão funcional real; não devem criar P-steps artificiais apenas para prolongar o projeto.

Consulte `PROJECT_COMPLETION_STATUS.md` e `execution/MT5_DEMO_RUNBOOK.md` para critérios operacionais e segurança.
