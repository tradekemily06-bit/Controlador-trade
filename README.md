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

O boundary HTTP possui rate limiting, limite de payload, request IDs, security headers, CSP e auditoria de eventos sem armazenamento do IP bruto ou do corpo da requisição. A trilha pode permanecer em memória ou, quando `CONTROLADOR_SECURITY_AUDIT_DB` é configurado, usar SQLite com retenção limitada para sobreviver a reinícios de uma instância. Falhas de persistência não derrubam o aplicativo. Armazenamento centralizado para múltiplas instâncias continua sendo responsabilidade da infraestrutura de produção.

## Integração DEMO

A primeira integração operacional escolhida é **IC Markets MT5 DEMO**. O adapter, o preflight somente leitura, os testes de segurança, o runbook e o fluxo controlado de primeira ordem já estão no projeto.

A validação operacional DEMO já foi concluída: uma ordem controlada de EURUSD 0,01 lote em COMPRA foi confirmada no IC Markets MT5 DEMO e posteriormente fechada pelo fluxo controlado. O identificador externo e o fechamento foram tratados pela camada de execução.

A integração cTrader DEMO permanece isolada como futura alternativa e não bloqueia o caminho MT5.

## Interface completa do ecossistema

A interface web responsiva integra os módulos:

- Painel operacional e decisão COMPRA/VENDA/AGUARDAR;
- Operação e estado fail-closed;
- Análise com score, ativo, timeframe, confirmação de candle e filtros;
- leitura técnica com os conceitos de tendência, estrutura, suporte/resistência, topos/fundos, volume, rompimento, pullback, pavio/rejeição, retirada de pavio, vela comando/força, GAB, DDT, pressão alta/baixa e taxa dívida;
- Laboratório & Replay;
- área de treinamento visual e análise de material fornecido;
- Memória, estatísticas e feedback WIN/LOSS/DRAW/OPEN/VOID;
- Risk Gate e proteções;
- Notícias & Contexto com boundary seguro e sem notícias inventadas;
- Configurações locais de preferência;
- Conexões, auditoria e segurança;
- navegação mobile-first para celular e notebook.

A interface continua em SIMULAÇÃO/DEMO e não possui caminho visual para habilitar REAL. As preferências salvas pela interface são locais ao navegador e não alteram a autorização de execução.

O manifest web é servido pelo próprio aplicativo e os endpoints possuem contratos automatizados.

## Validação

Para validação local, execute `python app.py` em um ambiente Python compatível e abra o endereço exibido pelo servidor. A suíte de testes cobre a interface e seus contratos; a verificação visual em dispositivos reais é uma validação de uso, não uma autorização de execução financeira.

## Estado do projeto

O software necessário para o núcleo, as fronteiras de execução DEMO, a integração IC Markets MT5 DEMO e a interface atual do ecossistema está implementado e coberto pela suíte de testes/CI. REAL permanece bloqueado.

Novos trabalhos devem ser motivados por uma necessidade concreta, defeito encontrado na validação ou expansão funcional real; não devem criar P-steps artificiais apenas para prolongar o projeto.
