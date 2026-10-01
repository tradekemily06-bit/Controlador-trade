# Controlador Trading — status de conclusão

## Estado atual

O estado de cada marco deve ser distinguido entre implementado no código, validado por testes/CI e validado fisicamente em runtime externo. O mapa macro não usa o número de P como porcentagem de conclusão: integração, testes e runtime são avaliados por evidência.

O núcleo técnico, as fronteiras de execução, a interface e a primeira camada de proteção SaaS do ecossistema estão implementados. A integração escolhida para a primeira validação operacional é **IC Markets MT5 DEMO**.

**Estado desta versão:** o repositório contém o caminho DEMO preparado e testado, mas a execução física de uma ordem DEMO não deve ser considerada comprovada apenas por documentação, testes com mocks ou CI. A confirmação física exige um terminal MetaTrader 5 compatível, conta DEMO conectada e evidência do preflight, `order_check()`, `order_send()`, identificador externo, fechamento e reconciliação.

## Integração macro consolidada

- P41–P46 possuem composição explícita em `ControlledAutomationService`, preservando as fronteiras individuais e sem conceder autoridade de execução.
- P44 exige `cycle_id` consistente entre ciclo de automação e `ExecutionIntent`.
- P48 impede observações de resultado anteriores ao fechamento do ciclo.
- P47–P53 permanecem ligados à cadeia factual de fechamento, reconciliação e aprendizado; P51/P52 só promovem registros reconciliados/VERIFIED a evidência.
- P120–P127 mantêm as fronteiras broker-agnostic de resultado, reconciliação, dados de mercado, ordem, sessão, Sandbox/DEMO e segurança pré-REAL.
- P127 mantém MT5 DEMO como integração operacional concreta; cTrader permanece isolado como alternativa futura.
- P128–P149 estão presentes no código como sequência posterior de integração/validação; não devem ser interpretados como 100% concluídos apenas pelo número: cada capacidade deve ser verificada por seus testes e runtime.

## Concluído no código/testes

- Núcleo de decisão independente de corretora/plataforma.
- Fluxo dados → análise → score/filtros → decisão → risco → execução → auditoria.
- Contratos de dados de mercado e execução.
- Gateway de execução com kill switch, bloqueio de duplicidade e comportamento fail-closed.
- Persistência/controle de estados de execução e tratamento explícito de `UNKNOWN`.
- Reconciliação externa.
- Validações de segurança antes de qualquer uso REAL.
- Boundary cTrader DEMO/OAuth preservada como integração futura.
- Adapter IC Markets MT5 DEMO.
- Preflight somente leitura para confirmar disponibilidade e conta DEMO.
- Testes de segurança do adapter e do preflight.
- Runbook para a primeira conexão MT5 DEMO.
- Interface web responsiva para celular e notebook.
- Risk Gate e proteções visíveis.
- Memória, estatísticas, replay e feedback operacional.
- CI com suíte de testes, auditoria de dependências e compilação.
- Proteções HTTP, request ID, rate limiting, limite de payload e CSP.
- Nenhuma credencial de conta deve ser persistida no repositório.

## Validação DEMO — estado verdadeiro

**Código/preparação: CONCLUÍDO.**

O preflight físico é somente leitura e confirma:
1. terminal MT5 inicializável;
2. conta realmente classificada como DEMO;
3. símbolo selecionável;
4. bid/ask disponíveis e válidos;
5. limites mínimo/step de volume.

A camada seguinte do adapter DEMO exige conta DEMO, símbolo/cotação válidos, volume compatível, `order_check()` aprovado, `order_send()` confirmado e identificador externo. A reconciliação consulta o histórico do MT5 e não reenviará uma ordem em caso de estado incerto.

**Validação física da primeira ordem: PENDENTE até existir evidência externa verificável.**

## REAL — estado verdadeiro

**EXECUÇÃO REAL: DESABILITADA.**

A arquitetura possui contratos e testes da fronteira pré-REAL, mas isso não equivale a autorização para operar dinheiro real.

Para uma futura liberação REAL ainda serão necessárias as condições de produção/identidade/segurança previstas pelo projeto, incluindo identidade confiável, isolamento durável por tenant/usuário, transporte seguro, gestão de segredos, auditoria durável, rate limiting centralizado e autorização REAL explícita.

Nenhuma interface, memória, replay, notícia, aprendizado ou análise pode habilitar REAL por conta própria.

## SaaS / produção

A primeira camada de hardening SaaS foi validada no CI. Ela não é, sozinha, um sistema completo de SaaS multiusuário: identidade, autorização, isolamento persistente, sessões, gestão de segredos e HTTPS de produção pertencem à infraestrutura de produção.

## Validação de dispositivo

A interface de software está implementada e coberta por testes de contrato. A abertura em navegador de um dispositivo real continua sendo validação de uso visual, não uma pendência de arquitetura.

## Regra de encerramento

Não criar novas etapas apenas para prolongar o projeto. Novas alterações devem ser motivadas por defeito concreto, necessidade funcional real, evidência externa de validação ou expansão funcional real.
