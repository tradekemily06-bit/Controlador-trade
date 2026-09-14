# Controlador Trading — status de conclusão

## Estado atual

O núcleo técnico, as fronteiras de execução, a interface, o modo de uso, as notificações e a camada de proteção SaaS do ecossistema estão implementados e validados pelo CI. A integração escolhida para a validação operacional é **IC Markets MT5 DEMO**.

A validação operacional DEMO foi executada com sucesso em ambiente compatível com MetaTrader 5: preflight, `order_check()`, primeira ordem controlada, confirmação do identificador externo, fechamento explícito e reconciliação foram concluídos sem habilitar REAL.

O projeto não deve criar novas P-steps apenas para prolongar o trabalho. A partir deste ponto, alterações devem responder a defeito concreto, requisito funcional real, endurecimento de segurança justificado ou expansão funcional deliberada.

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
- CI configurada para executar a suíte de testes, auditoria de dependências, compilação de todas as superfícies Python, build do container de produção e smoke test de saúde.
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
- Modo de Usar de primeira utilização, separado da operação e sem autoridade de execução.
- Reabertura do Modo de Usar sem adicionar item à navegação principal.
- Central de notificações priorizadas, com CRITICAL/IMPORTANT visíveis e INFO somente sob demanda.
- Proteção da publicação interna de atualizações por Bearer token configurado no ambiente; configuração ausente ou credencial inválida falha fechada.
- Compilação CI ampliada para `app.py`, `core`, `data`, `execution`, `audit`, `analysis`, `integration`, `security_guard.py`, `security_audit.py` e `web`.

## Validação de segurança SaaS

A camada atual de hardening SaaS foi validada no CI. Ela inclui boundary HTTP endurecido, auditoria bounded, proteção de atualização interna, identidade/tenant boundary e separação explícita entre o núcleo operacional e responsabilidades de infraestrutura de produção.

A trilha de auditoria registra metadados mínimos e não armazena IP bruto, credenciais, tokens ou corpos de requisição. SQLite é uma opção de persistência para uma instância; armazenamento centralizado e durável para múltiplas instâncias continua pertencendo à infraestrutura de produção.

A arquitetura também mantém separadas as responsabilidades de identidade confiável, contexto de tenant e autorização de operação. Isso não deve ser confundido com um provedor de autenticação completo: o status atual de produção continua indicando que o provedor de autenticação ainda precisa ser configurado em uma implantação SaaS real.

## Modo de Usar e notificações

O Modo de Usar explica onde ficam os módulos principais do ecossistema sem expor detalhes técnicos desnecessários e nunca recebe autoridade de execução. Pode ser reaberto a partir da área de configuração sem poluir a navegação principal.

A central de notificações separa criticidade. Eventos CRITICAL e IMPORTANT podem aparecer no resumo; notificações INFO ficam sob demanda para evitar poluição visual. A publicação interna de atualizações possui autenticação por token e não deve ser tratada como endpoint público de execução.

## Memória persistente de decisões

A memória continua funcionando sem configuração externa. Quando `CONTROLADOR_DECISION_DB` aponta para um arquivo SQLite gravável, decisões e outcomes sobrevivem ao reinício do processo. Falhas de persistência são tratadas de forma fail-soft e não habilitam execução financeira. Essa persistência local não substitui o futuro isolamento por usuário/tenant em uma implantação SaaS multiusuário.

## Validação de dispositivo

A interface de software está implementada e coberta por testes de contrato. A abertura no navegador de um dispositivo real continua sendo validação de uso visual; ela não é uma pendência de arquitetura, lógica de decisão ou execução DEMO.

## REAL

REAL permanece bloqueado. A existência do adapter DEMO não autoriza execução financeira real. Nenhum componente da interface, memória, replay, notícias, aprendizado ou análise pode habilitar REAL.

A camada de produção exige contexto de identidade/tenant confiável e armazenamento de produção adequado, e o contrato de REAL permanece explicitamente desabilitado. Não há atalho pela interface, memória, replay, aprendizado, notificações ou integrações DEMO.

## cTrader

cTrader permanece como alternativa futura e não bloqueia o projeto. A aprovação/autenticação do cTrader não é requisito para o funcionamento do caminho IC Markets MT5 DEMO.

## SaaS de produção

O núcleo possui boundaries preparados para identidade, tenant e armazenamento, mas uma implantação SaaS multiusuário de produção ainda exige infraestrutura real para autenticação, autorização, sessões seguras, isolamento persistente de dados, gestão de segredos e terminação HTTPS. Essas responsabilidades não devem ser improvisadas dentro do servidor mínimo atual.

Portanto, **SaaS foundation/hardening está implementado; SaaS multiusuário de produção ainda não está configurado**. Isso é uma distinção deliberada de segurança, não uma falha escondida no núcleo.

## Próxima expansão real

Se o ecossistema for transformado em SaaS multiusuário de produção, a próxima expansão genuína é conectar uma camada de identidade/autorização de produção e isolamento persistente de dados. Essa camada deve usar um provedor de identidade e um armazenamento apropriado, com autorização por usuário/tenant e sessões seguras, em vez de uma autenticação improvisada dentro do servidor mínimo atual.

Fora dessa expansão, não há motivo técnico para criar uma nova sequência artificial de P-steps. Integrações futuras, como cTrader, permanecem não bloqueantes.

## Regra de encerramento

Não criar novas etapas apenas para prolongar o projeto. Novas alterações devem ser motivadas por um defeito concreto, uma necessidade funcional real ou uma expansão funcional real.
