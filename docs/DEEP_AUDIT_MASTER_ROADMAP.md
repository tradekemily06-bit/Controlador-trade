# Auditoria profunda — roadmap mestre vivo

Este documento é o mapa de execução da auditoria profunda. A ordem é deliberada: primeiro preservar integridade e identidade, depois construir dependências de dados, depois integrar operação, e somente no fim fazer a rechecagem global. Itens adiados ficam registrados no `DEEP_AUDIT_DEFERRED_REGISTER.md` e não podem ser esquecidos.

## Invariantes permanentes

- Não existe limite funcional/produto artificial. Qualquer proteção numérica deve proteger um recurso, segurança ou risco real e ser documentada como tal.
- O professor/sênior começa disponível desde o primeiro uso do ecossistema com uma experiência profissional **45+ anos**. 45 é piso de experiência, nunca teto. A experiência não reinicia quando um novo usuário entra e pode crescer indefinidamente.
- O professor/sênior representa uma capacidade arquitetural de nível profissional, não uma pessoa humana nem uma certificação inventada. Conhecimento e competências precisam de fontes, validação, testes e histórico de atualização.
- O professor/sênior cobre tanto **gestão de riscos** quanto **gestão financeira** em nível profissional, inclusive para operação manual e tomada de decisão humana; isso não concede autoridade de execução.
- Professor/sênior nunca recebe autoridade de execução por ser sênior. Julgamento, risco, segurança, identidade e execução continuam separados.
- REAL permanece bloqueado até que todos os gates independentes de produção estejam configurados e validados.
- Quando uma dependência externa estiver indisponível, registrar o estado e continuar tudo que não depende dela; nunca apagar o requisito nem tratá-lo como concluído.
- Nenhuma decisão, aprendizado, resultado ou preferência de um usuário pode atravessar a fronteira de outro usuário/tenant.

## Ordem oficial

### FASE A — Integridade e mapa de auditoria

**A1. Baseline e inventário** — EM ANDAMENTO
- confirmar branch/PR/base/head;
- manter matriz de endpoints, estado e risco;
- procurar limites artificiais, estado global, mutações e caminhos de execução;
- manter documentação sincronizada com o código real.

**A2. Propriedade e identidade de dados** — PARCIALMENTE RESOLVIDO
- `DecisionRecord` com `subject_id` + `tenant_id`;
- repository tenant+subject scoped;
- identidade confiável WSGI;
- fail-closed sem data plane tenant-scoped;
- integrar definitivamente os endpoints de mutação/leitura ao boundary.

**A3. Atomicidade e recuperação** — PARCIALMENTE RESOLVIDO
- replay pré-validado e persistência em lote;
- estados UNKNOWN/reconciliação;
- impedir efeitos parciais e resultados inventados;
- verificar todas as superfícies equivalentes.

### FASE B — Data plane SaaS real

**B1. Armazenamento durável tenant-scoped** — PENDENTE
- contrato de produção compartilhado;
- isolamento por tenant e sujeito;
- índices/consultas corretos;
- migração sem perda silenciosa;
- consistência, concorrência e recuperação.

**B2. HTTP → identidade → serviço → armazenamento** — PENDENTE
- `/api/analyze`;
- `/api/replay`;
- `/api/outcome`;
- memória e estatísticas;
- preferências;
- notificações;
- aprendizagem;
- qualquer nova superfície futura.

**B3. Estado por usuário/tenant** — PENDENTE
- remover dependência de estado global de processo para SaaS;
- preservar o modo local/teste separado;
- testar isolamento cruzado e não divulgação de existência.

### FASE C — Conhecimento profissional do professor/sênior

**C1. Experiência profissional inicial** — RESOLVIDO
- piso 45+;
- primeiro dia do usuário separado da experiência acumulada;
- sem teto artificial;
- crescimento futuro permitido.

**C2. Currículo financeiro profissional** — BASE EXISTENTE / VALIDAÇÃO E PROVENIÊNCIA PENDENTES
O currículo já cobre uma trilha ampla de educação financeira, sistema financeiro, renda fixa, ações/fundos/ETFs, derivativos, microestrutura, price action, fundamental, macro, quantitativo, carteiras, risco, metodologias, psicologia, execução, automação, regulação/ética, prática profissional e pesquisa contínua.

Próximo trabalho: transformar esse mapa em uma matriz de conhecimento profissional auditável: `domínio → competência → fonte → versão/data → validação → teste → evidência → status → atualização`. Não declarar cursos, diplomas ou certificações que não existam.

**C3. Gestão de riscos profissional** — BASE EXISTENTE / EXPANSÃO CONTÍNUA
O sênior deve raciocinar sobre risco de capital, posição, drawdown, alavancagem/margem, concentração, correlação, liquidez, custos, execução, cenários adversos, incerteza e recuperação. Isso vale para operação automatizada **e manual**: o usuário precisa conseguir aprender a gerir o próprio risco como trader profissional.

**C4. Gestão financeira profissional** — INICIADA / VALIDAÇÃO PENDENTE
Inclui gestão de capital, orçamento, fluxo de caixa, reserva de liquidez, alocação, dimensionamento de posição, concentração, drawdown, alavancagem, custos, desempenho, portfólio, contingência, registros e organização financeira relacionada à atividade de trading. A gestão financeira deve distinguir dinheiro disponível, capital destinado ao trading, capital em risco, liquidez de reserva, exposição e resultado realizado/não realizado.

Foi adicionada uma capacidade analítica inicial em `core/senior_financial_management.py`, sem autoridade de execução. A próxima etapa é integrar essa capacidade ao currículo, ao raciocínio sênior, ao risco e ao ensino, com fontes e validações.

**C5. Conhecimento operacionalmente seguro** — PENDENTE
- separar conhecimento estudado de conhecimento validado;
- manter contraevidência e incerteza;
- promoção controlada para uso operacional;
- nenhuma promoção concede execução REAL.

### FASE D — Valor monetário de pontos/ticks/pips e alavancagem

**D1. PointValueEngine central** — EM IMPLEMENTAÇÃO
- normalizar ponto/tick/pip conforme instrumento;
- usar especificação do broker/instrumento;
- calcular valor monetário por unidade de movimento e quantidade;
- converter para moeda da conta quando necessário;
- anexar timestamp, frescor e proveniência;
- exigir REASSESS/AGUARDAR quando o cálculo depender de conversão desatualizada.

**D2. Integração** — PENDENTE
- operação normal;
- risco;
- position sizing;
- exposição;
- distância de stop;
- P/L estimado;
- alavancagem;
- replay/laboratório com especificações históricas quando disponíveis.

**D3. Alavancagem sem dupla contagem** — PENDENTE
- valor do ponto não é multiplicado pela alavancagem;
- alavancagem altera exposição/margem/relação de capital conforme o modelo do broker;
- revisar `margin_required`, atualmente simplificado, contra especificação real do instrumento/broker.

### FASE E — Replay, escala e recursos

**E1. Replay sem teto funcional** — RESOLVIDO no núcleo
- antigo teto 50 removido;
- pré-validação e persistência atômica;
- manter a regra para futuras extensões.

**E2. Custo real** — PENDENTE
- tamanho estrutural;
- CPU/tempo;
- memória;
- volume de registros;
- concorrência;
- cancelamento/recuperação;
- armazenamento;
- paginação/streaming/assíncrono quando necessário.

**E3. Proteções distribuídas** — PENDENTE
- rate limit compartilhado;
- retenção/auditoria centralizada;
- observabilidade multi-réplica.

### FASE F — Segurança SaaS completa

**F1. Sessão/autenticação/autorização reais** — PENDENTE de deployment/provider
- identidade não pode vir do navegador;
- RBAC e tenant isolation;
- CSRF quando houver cookies/sessão;
- rotação/revogação e recuperação.

**F2. Superfícies de estado** — PENDENTE
- outcome;
- preferences;
- notifications;
- learning;
- memory/statistics;
- status/health;
- qualquer endpoint novo.

**F3. Supply chain e runtime** — PARCIALMENTE RESOLVIDO
- CI/security audit/compile/build/smoke;
- pinagem imutável;
- dependências de runtime/teste separadas;
- continuar rechecando após mudanças.

### FASE G — Integrações e execução controlada

**G1. Dados e broker** — CONTÍNUO
- núcleo broker-agnostic;
- adaptadores nas bordas;
- DEMO primeiro;
- nenhuma dependência bloqueante desnecessária.

**G2. REAL** — BLOQUEADO POR DESIGN
Só considerar liberação depois de identidade/auth/session, tenant data plane durável, autorização, risco, segurança, admission, ledger, reconciliação, observabilidade e testes de produção estarem todos comprovados.

**G3. cTrader** — DEFERIDO / NÃO BLOQUEANTE
Registrar o requisito e continuar com as partes independentes.

### FASE H — Produto e experiência do usuário

**H1. Modo de Usar** — INTEGRADO
- primeiro uso guiado;
- mostra onde cada coisa está;
- detalhes técnicos ficam ocultos;
- pode ser reaberto sem poluir a navegação.

**H2. Notificações** — INTEGRADO / CONTÍNUO
- CRITICAL/IMPORTANT visíveis;
- INFO sob demanda;
- alertas de atualização/materialidade;
- nunca deixar uma notificação importante escondida por preferência comum.

**H3. UI sem poluição** — CONTÍNUO
- operações principais visíveis;
- detalhes avançados sob demanda;
- nenhuma interface pode contornar gates de segurança.

### FASE I — Validação final

**I1. Testes funcionais e regressão**

**I2. Segurança e isolamento**

**I3. Integridade de dados e recuperação**

**I4. Limites artificiais / busca global de `MAX_*`, quotas, slices e defaults**

**I5. CI, dependências, compileall, container e smoke**

**I6. Auditoria de documentação versus código**

**I7. Governança do PR: aprovação, CI e branch protection**

**I8. CHECAGEM GERAL final pós-governança**

Só aqui a auditoria é declarada encerrada.

## Regra de retorno

Se uma fase precisar parar por integração, configuração ou aprovação externa, o trabalho não é perdido. O item permanece no registro de pendências com o estado exato e a próxima ação. A próxima execução retoma do primeiro item não resolvido da ordem, sem apagar requisitos posteriores.
