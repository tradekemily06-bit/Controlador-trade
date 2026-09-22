# Stage 7 — Check-up Geral Final

Esta matriz é uma auditoria independente. Ela não assume que uma etapa anterior está correta só porque possui testes ou documentação.

## 1. Arquitetura e caminhos

- [ ] decisão → risco → gateway → adapter → ledger → reconciliação permanece único;
- [ ] nenhum side door de execução direta foi reintroduzido;
- [ ] factories e registries não reexpõem adapters privilegiados;
- [ ] caminhos legados são classificados: seguro, bloqueado ou migrado;
- [ ] restart e múltiplas instâncias preservam a mesma autoridade.

## 2. Segurança e identidade

- [ ] origem de privilégios REAL continua autenticada por issuer interno;
- [ ] request_id, symbol, broker_id e adapter_id permanecem vinculados;
- [ ] snapshot/risk identity e freshness são revalidados no ponto final;
- [ ] kill switch, incidente, manutenção e barreiras globais são fail-closed;
- [ ] nenhuma UI/API/configuração cria privilégio REAL.

## 3. Execução e DEMO/REAL

- [ ] DEMO é testável sem qualquer acesso ao caminho REAL;
- [ ] REAL continua explicitamente bloqueado durante esta revisão;
- [ ] adapter identity é confirmada antes/depois do dispatch;
- [ ] external_id é obrigatório para confirmação;
- [ ] timeout, exceção ou resposta ambígua produzem UNKNOWN quando o envio pode ter ocorrido.

## 4. Persistência e recuperação

- [ ] ledger, lifecycle, safety, incident e checkpoint suportam restart seguro;
- [ ] corrupção/truncamento/schema desconhecido falham fechando;
- [ ] RESERVED/UNKNOWN nunca recebem replay automático;
- [ ] reconciliação exige autoridade e evidência vinculada;
- [ ] locks cobrem os pontos sujeitos a TOCTOU.

## 5. Observabilidade e auditoria

- [ ] request/correlation identity atravessa o fluxo;
- [ ] BLOCKED/UNKNOWN/ACCEPTED/RECONCILED são distinguíveis;
- [ ] segredos, tokens e credenciais são redigidos;
- [ ] health/readiness é somente observabilidade;
- [ ] falha de observabilidade não autoriza execução.

## 6. Produto/SaaS

- [ ] Operação, Análise, Memória, Laboratório/Replay e Ensino permanecem separados;
- [ ] onboarding e notificações não alteram autorização;
- [ ] dados persistentes possuem escopo de tenant/usuário quando aplicável;
- [ ] UI mobile-first não esconde estados críticos;
- [ ] falha da camada de produto não derruba nem contorna as barreiras.

## 7. Operação e release

- [ ] CI consolidado está verde no commit efetivamente auditado;
- [ ] dependências e imagens foram revisadas;
- [ ] configuração/secrets de produção foram revisados sem expor valores;
- [ ] rollback foi exercitado;
- [ ] incident response, kill switch e reconciliação possuem runbook testável;
- [ ] mudança de capacidade REAL exige aprovação explícita e separada.

## Regra de conclusão

Stage 7 só pode ser marcada como concluída quando **todos** os itens acima tiverem evidência executável, atual e rastreável. Documentação sem execução não fecha um item.

Mesmo com a matriz completa, Stage 7 não habilita REAL. Ela somente determina se o ecossistema está pronto para uma revisão deliberada de release.
