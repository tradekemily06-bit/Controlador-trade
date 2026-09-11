# Controlador Trading — status de conclusão

## Estado atual

O núcleo técnico, as fronteiras de execução, a interface e a primeira camada de proteção SaaS do ecossistema estão implementados. A integração escolhida para a primeira validação operacional é **IC Markets MT5 DEMO**.

A validação operacional DEMO foi executada com sucesso em ambiente compatível com MetaTrader 5: preflight, `order_check()`, primeira ordem controlada, confirmação do identificador externo, fechamento explícito e reconciliação foram concluídos sem habilitar REAL.

## Concluído

- Núcleo de decisão independente de corretora/plataforma.
- Fluxo dados → análise → score/filtros → decisão → risco → execução → auditoria.
- Contratos de dados de mercado e execução.
- Gateway de execução com kill switch, bloqueio de duplicidade e comportamento fail-closed.
- Persistência/controle de estados de execução e tratamento explícito de `UNKNOWN`.
- Reconciliação externa.
- Validações de segurança antes de qualquer uso REAL.
- Boundary cTrader DEMO/OAuth preservada como integração futura, sem bloquear o projeto.
- Adapter IC Markets MT5 DEMO.
- Preflight somente leitura para confirmar disponibilidade e conta DEMO.
- Testes de segurança do adapter e do preflight.
- Runbook para a primeira conexão MT5 DEMO.
- Primeira ordem DEMO controlada em EURUSD, 0,01 lote, COMPRA, confirmada e depois fechada de forma controlada.
- Interface web responsiva para celular e notebook.
- Painel operacional.
- Módulo Operação e estado fail-closed.
- Módulo Análise com score, ativo, timeframe, confirmação e filtros.
- Catálogo visual dos conceitos de leitura e estudo definidos para o ecossistema.
- Laboratório & Replay.
- Área de treinamento visual e análise de material fornecido.
- Memória, estatísticas e feedback WIN/LOSS/DRAW/OPEN/VOID.
- Persistência opcional da memória de decisões em SQLite, com restauração na inicialização e atualização persistente de outcomes.
- Risk Gate e proteções visíveis.
- Notícias & Contexto com boundary seguro e sem dados inventados.
- Configurações locais de preferência.
- Conexões, auditoria e segurança.
- Navegação mobile-first.
- APIs de status, análise, replay, memória, estatísticas, risco, notícias/contexto e conexões.
- Manifest web servido pelo aplicativo.
- Contratos automatizados para a interface e APIs.
- CI configurada para executar a suíte de testes, auditoria de dependências e compilação do projeto.
- Rate limiting por cliente no boundary HTTP.
- Limite de payload JSON de 256 KiB.
- Request ID para rastreabilidade.
- Security headers e CSP básica.
- Erros HTTP sem exposição de detalhes internos.
- Dependabot para dependências Python e GitHub Actions.
- Dependência futura do cTrader isolada do ambiente base, evitando que uma integração não utilizada enfraqueça a auditoria de segurança do núcleo.
- Nenhuma credencial de conta deve ser persistida no repositório.
- Trilha de auditoria HTTP bounded e privacy-conscious.
- Persistência opcional da trilha de auditoria em SQLite, com retenção limitada e fallback em memória.

## Validação de segurança SaaS

A primeira camada de hardening SaaS foi validada no CI: testes de robustez, suíte completa, `pip-audit` e compilação concluíram com sucesso.

A trilha de auditoria registra metadados mínimos e não armazena IP bruto, credenciais, tokens ou corpos de requisição. SQLite é uma opção de persistência para uma instância; armazenamento centralizado e durável para múltiplas instâncias continua pertencendo à infraestrutura de produção.

Essa camada é uma proteção de boundary HTTP e **não é, sozinha, um sistema completo de SaaS multiusuário**. Autenticação, autorização, isolamento por tenant/usuário, sessões persistentes, gestão de segredos e terminação HTTPS continuam pertencendo à próxima camada de infraestrutura/identidade de produção.

## Memória persistente de decisões

A memória continua funcionando sem configuração externa. Quando `CONTROLADOR_DECISION_DB` aponta para um arquivo SQLite gravável, decisões e outcomes sobrevivem ao reinício do processo. Falhas de persistência são tratadas de forma fail-soft e não habilitam execução financeira. Essa persistência local não substitui o futuro isolamento por usuário/tenant em uma implantação SaaS multiusuário.

## Validação de dispositivo

A interface de software está implementada e coberta por testes de contrato. A abertura no navegador de um dispositivo real continua sendo validação de uso visual; ela não é uma pendência de arquitetura, lógica de decisão ou execução DEMO.

## REAL

REAL permanece bloqueado. A existência do adapter DEMO não autoriza execução financeira real. Nenhum componente da interface, memória, replay, notícias, aprendizado ou análise pode habilitar REAL.

## cTrader

cTrader permanece como alternativa futura e não bloqueia o projeto. A aprovação/autenticação do cTrader não é requisito para o funcionamento do caminho IC Markets MT5 DEMO.

## Próxima expansão real

Se o ecossistema for transformado em SaaS multiusuário de produção, a próxima expansão genuína é conectar uma camada de identidade/autorização de produção e isolamento persistente de dados. Essa camada deve usar um provedor de identidade e um armazenamento apropriado, com autorização por usuário/tenant e sessões seguras, em vez de uma autenticação improvisada dentro do servidor mínimo atual.

## Regra de encerramento

Não criar novas etapas apenas para prolongar o projeto. Novas alterações devem ser motivadas por um defeito concreto, uma necessidade funcional real ou uma expansão funcional real.
