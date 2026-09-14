# Auditoria profunda — integridade de dados e fronteira HTTP

## Escopo

Esta auditoria cobre a superfície HTTP atual, mutações de estado, memória/estatísticas, aprendizagem, replay, auditoria de segurança e cadeia de build do container.

## Matriz de risco atual

| Superfície | Tipo | Estado atual | Risco | Tratamento |
|---|---|---|---|---|
| `/api/health` | GET | health público | exposição operacional | em SaaS público retorna somente `ok: true`; detalhes continuam fora da superfície pública |
| `/api/status` | GET | leitura operacional | exposição de estado | em SaaS público exige identidade confiável + tenant-scoped data plane |
| `/api/notifications`, `/api/notifications/all` | GET | leitura | baixa | em SaaS público exige identidade + tenant data plane; conteúdo renderizado com escape no frontend |
| `/api/updates` | POST | mutação interna | alta se exposta | protegido por `CONTROLADOR_UPDATE_TOKEN` e fail-closed quando não configurado |
| `/api/analyze` | POST | grava decisão/memória | média em API pública | em modo SaaS público exige identidade confiável e tenant-scoped data plane; como este último ainda não existe, falha fechado |
| `/api/replay` | POST | grava decisões na memória atual | média/alta | limite explícito de 50 casos por requisição + limite de corpo; ainda depende de tenant-scoped storage para SaaS público |
| `/api/outcome` | POST | altera resultado de decisão | alta para integridade | protegido pelo gate de identidade em SaaS público, mas propriedade da decisão/tenant ainda precisa ser integrada ao fluxo HTTP; sem isso, o modo SaaS público falha fechado |
| `/api/preferences*` | GET/POST | mutação/leitura de preferências | média | identidade + tenant são requisitos de SaaS; modo público falha fechado até existir armazenamento tenant-scoped |
| `/api/learning/*` | GET/POST | estado de aprendizagem | média/alta | identidade + tenant são requisitos de SaaS; validação/admissão exige `admin`; modo público falha fechado sem data plane |
| `/api/risk`, `/api/news`, `/api/connections` | GET | estado operacional | média | em SaaS público exige identidade + tenant data plane |
| `/api/saas/status` | GET | estado SaaS | média | em SaaS público exige identidade + tenant data plane |

## Achados confirmados

### 1. REAL continua isolado

A superfície HTTP não possui rota pública de execução REAL. A camada de execução REAL exige contratos próprios e permanece desabilitada. Nenhuma das mutações auditadas cria autoridade de execução.

### 2. Aprendizagem não autoriza trading

As respostas HTTP de aprendizagem continuam explicitando `execution_allowed: false` ou `operation_eligible: false`, e o serviço mantém a regra de que conhecimento externo não concede autoridade de operação.

### 3. Fronteira provider-neutral de identidade foi introduzida

O modo `CONTROLADOR_SAAS_PUBLIC=true` agora exige identidade injetada pelo ambiente WSGI confiável para mutações sensíveis. Cabeçalhos HTTP `X-*` não são tratados como identidade confiável. A camada também separa papel administrativo das ações de validação/admissão de aprendizagem.

### 4. SaaS público falha fechado sem armazenamento tenant-scoped

Mesmo uma identidade confiável não libera acesso ao estado atual, porque memória, decisões, preferências e aprendizagem ainda são globais ao processo. O gate de SaaS público exige um data plane tenant-scoped real e retorna indisponibilidade enquanto ele não existir. Isso evita transformar autenticação sem isolamento em falsa segurança multiusuário.

### 5. Leituras globais também foram fechadas

A auditoria encontrou uma lacuna adicional: proteger apenas POST não era suficiente, porque GETs de memória, estatísticas, preferências, aprendizagem, conexões e status ainda poderiam expor estado global. Essas leituras agora também exigem identidade confiável e data plane tenant-scoped quando o modo SaaS público está ativo.

### 6. Health público foi sanitizado

`/api/health` continua disponível para infraestrutura e smoke tests, mas em modo SaaS público retorna somente `ok: true`. Detalhes como armazenamento, identidade e estado interno não são expostos nessa superfície.

### 7. Propriedade de DecisionRecord foi endurecida

`DecisionRecord` agora possui `subject_id` e `tenant_id` como metadados de propriedade e oferece vínculo único por `with_owner()`: uma decisão já vinculada não pode ser reatribuída a outro sujeito/tenant. `owned_by()` exige correspondência exata. Esses valores continuam sendo confiáveis somente quando atribuídos por uma fronteira de identidade confiável; o navegador nunca é prova de identidade.

### 8. Repositório tenant-scoped falha fechado sem proprietário

`ProductionTenantDecisionRepository` agora exige que o `tenant_id` do registro corresponda ao tenant confiável e rejeita registros sem `subject_id`. Leituras também verificam o tenant armazenado e a presença de proprietário. Isso fecha o risco de transformar apenas o `decision_id` em autorização.

### 9. DecisionStore local não finge ser produção

O `DecisionStore` continua explicitamente classificado como armazenamento local. O schema foi ampliado para persistir `subject_id`/`tenant_id`, possui migração para bancos legados e cria índice de tenant. Quando um banco é configurado, falhas de inicialização, leitura ou escrita agora falham explicitamente em vez de apagar silenciosamente a durabilidade e continuar como se tudo estivesse salvo.

Isso não transforma SQLite local em armazenamento SaaS: o data plane de produção continua sendo o contrato tenant-scoped separado.

### 10. Resultado de operação ainda precisa de integração com proprietário

`/api/outcome` continua podendo alterar um `decision_id` no modo local de usuário único. A camada de dados agora possui os mecanismos necessários para verificar propriedade, mas o fluxo HTTP normal ainda não foi migrado para o repositório tenant-scoped. Em SaaS público, o gate continua bloqueando antes de chegar ao estado global.

### 11. Replay agora tem limite explícito

`/api/replay` aceita no máximo 50 casos por requisição. O limite é complementar ao teto de corpo de 256 KiB e preserva o laboratório atual. Ainda é necessário um modelo de custo/timeout mais forte quando houver processamento de replay pesado ou distribuído.

### 12. Auditoria de segurança é limitada e sem segredo bruto

O trilho guarda no máximo 1000 eventos em memória/SQLite, corta o path a 512 caracteres e guarda hash do identificador do cliente, não IP bruto, credencial, token ou corpo. A retenção centralizada multi-instância pertence à infraestrutura de produção.

### 13. Rate limit é por processo

O limite atual é 60 requisições por 60 segundos e no máximo 10.000 clientes rastreados. Isso é adequado como barreira local, mas não é uma proteção distribuída para múltiplas réplicas.

### 14. Cadeia de build foi endurecida

Foi adicionado `.dockerignore` para excluir `.runtime`, bancos SQLite, `.env`, logs, caches e artefatos Git/dev do contexto Docker. Isso evita copiar acidentalmente estado local ou arquivos de segredo para a imagem durante um build feito a partir de uma árvore de trabalho contaminada.

### 15. Publicação foi explicitamente classificada

`README_DEPLOY.md` deixa explícito que a publicação atual é para teste/uso controlado, não uma implantação SaaS multiusuário de produção. O modo SaaS público permanece deliberadamente bloqueado até existir autenticação/sessão real, autorização, tenant isolation e armazenamento compartilhado/tenant-scoped.

## Não corrigir artificialmente

Não devem ser criados atalhos para habilitar REAL, nem considerar um booleano enviado pelo navegador como prova de identidade, validação de conhecimento, autorização administrativa ou propriedade de uma decisão. Essas garantias devem vir de uma fronteira de confiança real.

## Próxima correção técnica prioritária

1. Conectar o fluxo HTTP normal a um data plane tenant-scoped real.
2. Propagar `subject_id` + `tenant_id` da identidade confiável até `analyze`, `replay`, `memory`, `statistics` e `outcome`.
3. Fazer `/api/outcome` carregar a decisão por tenant e verificar propriedade antes de alterar o resultado.
4. Separar definitivamente armazenamento de teste/local do armazenamento compartilhado de produção.
5. Adicionar limites de custo/timeout para replay além do limite de quantidade.
6. Substituir rate limit em memória por mecanismo compartilhado quando houver múltiplas réplicas.
7. Revisar ações do CI para pinagem imutável por SHA e separar dependências de runtime/teste.
8. Manter REAL bloqueado até todos os gates de produção estarem configurados e validados.
