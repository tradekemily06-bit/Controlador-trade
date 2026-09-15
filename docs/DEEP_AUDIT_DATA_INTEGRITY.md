# Auditoria profunda — integridade de dados e fronteira HTTP

## Escopo

Esta auditoria cobre a superfície HTTP atual, mutações de estado, memória/estatísticas, aprendizagem, replay, auditoria de segurança, limites funcionais, alavancagem/ponto monetário e cadeia de build.

## Estado consolidado

| Superfície | Estado | Observação |
|---|---|---|
| `/api/health` | PROTEGIDO | Em SaaS público expõe somente o mínimo necessário para infraestrutura. |
| `/api/status` | PROTEGIDO / DEPENDENTE | Exige identidade confiável e data plane tenant-scoped no modo público. |
| `/api/analyze` | PROTEGIDO / DEPENDENTE | Identidade e ownership já existem no serviço; SaaS público permanece fechado sem data plane real. |
| `/api/replay` | PROTEGIDO / DEPENDENTE | Pré-validação + persistência em lote; **sem limite funcional artificial de quantidade**. |
| `/api/outcome` | PENDENTE DE INTEGRAÇÃO | Precisa usar o repositório tenant+subject scoped antes de mutar resultado em SaaS. |
| `/api/preferences*` | PENDENTE DE DATA PLANE | Não pode usar estado global como fonte de verdade em SaaS multiusuário. |
| `/api/notifications*` | PENDENTE DE DATA PLANE | Conteúdo prioritário existe; persistência/isolamento por usuário ainda depende do data plane. |
| `/api/learning/*` | PROTEGIDO / DEPENDENTE | Identidade/admin/proveniência precisam permanecer confiáveis; SaaS público falha fechado sem data plane. |
| `/api/updates` | PROTEGIDO | Publicação interna exige token de atualização e falha fechado sem configuração. |
| REAL | BLOQUEADO | Não há rota pública de REAL e as camadas próprias continuam desabilitadas. |

## Ownership e tenant isolation

`DecisionRecord` possui `subject_id` e `tenant_id` e pode receber ownership apenas por uma fronteira confiável. `owned_by()` exige correspondência exata e `with_owner()` impede reatribuição silenciosa de uma decisão já vinculada.

`ProductionTenantDecisionRepository` exige tenant e sujeito confiáveis, verifica ownership do registro e falha fechado diante de dados inconsistentes. Wrong-subject reads devem evitar existência-oracle quando possível.

O modo `CONTROLADOR_SAAS_PUBLIC` continua bloqueando o uso de estado global enquanto o data plane tenant-scoped real não existir. Isso é deliberado: autenticar sem isolar os dados não é segurança multiusuário.

## Replay e capacidade

O Replay não possui teto funcional de quantidade de cenários. O antigo limite 50 foi removido. A pré-validação estrutural acontece antes da análise e a persistência é feita em lote, de modo que falhas não deixem histórico parcial.

Proteções de infraestrutura podem existir para corpo HTTP, memória, CPU, tempo, concorrência, armazenamento, abuso e disponibilidade. Essas proteções não devem ser apresentadas como limite funcional de cenários, candles, operações ou capacidade do produto.

Quando uma resposta for grande demais para processamento síncrono, a arquitetura correta é paginação/cursor, streaming, processamento assíncrono, cancelamento ou outro mecanismo baseado no recurso real — não um teto funcional arbitrário.

## Limites: classificação obrigatória

- quotas funcionais de planos: removidas;
- quantidade de cenários de replay: sem teto funcional;
- `limit` de paginação/apresentação: controle de transporte/consulta, não capacidade comercial;
- tamanho de corpo: proteção de recurso;
- rate limit: anti-abuso/disponibilidade;
- retenção local de auditoria: cache operacional, não capacidade de produto;
- limites de risco de trading: controles de segurança/risco, preservados;
- frescor de dados: integridade/safety, não capacidade.

Qualquer novo `MAX_*`, `limit`, quota, slice ou truncamento deve ser classificado antes de ser aceito.

## Professor/sênior

O ecossistema mantém um perfil sênior disponível desde o primeiro dia do usuário com piso de **45+ anos de experiência**. Esse valor é um piso arquitetural, não um limite superior: a experiência pode crescer indefinidamente e não é reiniciada pela entrada de um novo usuário.

O perfil não é uma alegação de que exista uma pessoa humana nem uma certificação inventada. O currículo financeiro profissional já cobre fundamentos, sistema financeiro, instrumentos, microestrutura, price action, fundamental, macro, quantitativo, carteiras, risco, metodologias, psicologia, execução, automação, regulação/ética, prática profissional e pesquisa contínua.

A pendência é elevar esse currículo a uma matriz auditável de conhecimento: domínio → competência → fonte → versão/data → validação → teste → evidência → status → atualização. Nenhuma certificação, diploma ou curso deve ser declarado como concluído sem evidência real.

Ser sênior nunca equivale a autorização de execução. O professor pode raciocinar, pesquisar, ensinar, questionar e avaliar risco; execução permanece atrás de suas próprias fronteiras.

## Ponto/tick/pip e alavancagem

Foi criada uma fronteira central `PointValueEngine` para transformar movimento de preço em valor monetário sem transformá-lo em sinal de COMPRA/VENDA.

O engine usa, conforme disponibilidade e proveniência, valor de tick do broker, especificação contratual ou valor explícito de unidade de preço; normaliza tick/point/pip, quantidade e conversão para a moeda da conta e carrega timestamp/frescor da conversão.

Quando uma conversão cambial necessária está stale, o resultado é `REASSESS` e não usa silenciosamente a taxa antiga. A alavancagem pode consumir esse resultado, mas não multiplica o valor do ponto pela alavancagem. Alavancagem e valor monetário do movimento são dimensões separadas.

A fórmula de `margin_required` ainda precisa ser confrontada com a especificação real de cada instrumento/broker antes de ser considerada um modelo universal.

## Segurança de aprendizagem

Conteúdo externo deve continuar sendo tratado como alegação até validação. `content_verified`, `security_checked` ou `knowledge_validated` vindos diretamente de um cliente não podem ser considerados prova de confiança em SaaS de produção. A fronteira administrativa/proveniência deve ser mantida no data plane confiável.

Aprendizagem continua sem autoridade de execução.

## Auditoria de segurança e rate limit

A retenção local de eventos de segurança e o rate limit em processo são barreiras de recurso/anti-abuso, não limites funcionais do ecossistema. Em múltiplas réplicas, a autoridade definitiva deve migrar para mecanismos compartilhados na infraestrutura de produção.

## Cadeia de build

O build usa `.dockerignore` para excluir estado local, SQLite, `.env`, logs, caches e artefatos de desenvolvimento. CI mantém testes, auditoria de dependências, compilação de todas as superfícies Python, build de produção e smoke test.

## Critérios de fechamento

Esta auditoria só pode ser encerrada após:

1. data plane durável tenant+subject scoped integrado;
2. `/api/outcome` protegido por ownership no fluxo real;
3. memória, estatísticas, preferências, notificações e aprendizagem isoladas por usuário/tenant;
4. currículo sênior com provenance/validação/testes;
5. PointValueEngine integrado à operação, risco e alavancagem;
6. modelo de margem revisado por especificação de instrumento/broker;
7. replay protegido por custo real sem teto funcional;
8. rate limit/auditoria compartilhados para múltiplas réplicas;
9. autenticação/sessão/RBAC/CSRF de produção quando aplicáveis;
10. CI/security/compile/container/smoke verdes após todas as mudanças;
11. documentação sincronizada com código e testes;
12. governança do PR satisfeita;
13. CHECAGEM GERAL final pós-governança.

REAL permanece bloqueado até esses critérios serem comprovados.
