# Auditoria profunda — integridade de dados e fronteira HTTP

## Escopo

Esta auditoria cobre a superfície HTTP atual, mutações de estado, memória/estatísticas, aprendizagem, replay, auditoria de segurança e cadeia de build do container.

## Matriz de risco atual

| Superfície | Tipo | Estado atual | Risco | Tratamento |
|---|---|---|---|---|
| `/api/health`, `/api/status` | GET | leitura | exposição operacional | aceitável para health; produção deve sanitizar detalhes conforme modelo de usuário |
| `/api/notifications`, `/api/notifications/all` | GET | leitura | baixa | conteúdo renderizado com escape no frontend |
| `/api/updates` | POST | mutação interna | alta se exposta | protegido por `CONTROLADOR_UPDATE_TOKEN` e fail-closed quando não configurado |
| `/api/analyze` | POST | grava decisão/memória | média em API pública | sem autenticação/tenant na borda atual; não concede execução |
| `/api/replay` | POST | grava decisões na memória atual | média/alta | limite de corpo existe; quantidade de casos ainda deve ser explicitamente limitada em endurecimento futuro |
| `/api/outcome` | POST | altera resultado de decisão | alta para integridade | endpoint atual não tem identidade/tenant; não concede execução, mas pode corromper estatísticas se publicado como SaaS multiusuário |
| `/api/preferences*` | POST | mutação de preferências | média | estado atualmente compartilhado pelo processo; precisa de identidade/tenant antes de SaaS multiusuário |
| `/api/learning/resources` | POST | grava material | média | conteúdo externo permanece sem autoridade de execução |
| `/api/learning/sources/screen` | POST | cria fonte | média | gate rejeita esquemas diferentes de HTTPS |
| `/api/learning/sources/validate` | POST | muda fonte para VALIDATED | alta para integridade | atualmente aceita `content_verified` e `security_checked` do chamador; deve ficar atrás de identidade/autorização administrativa em SaaS |
| `/api/learning/sources/admit` | POST | marca conhecimento validado | alta para integridade | atualmente aceita `knowledge_validated` do chamador; não concede operação, mas precisa de autoridade confiável em SaaS |
| `/api/learning/observations` | POST | grava observação | média | observação validada exige fonte validada e conhecimento validado |
| `/api/learning/professor/activity` | POST | gera atividade | média | continua sem autoridade de trading; a validação informada pelo chamador ainda é uma fronteira de confiança |
| `/api/learning/attempts` | POST | grava tentativa | baixa/média | precisa de escopo por usuário quando houver SaaS multiusuário |

## Achados confirmados

### 1. REAL continua isolado

A superfície HTTP não possui rota pública de execução REAL. A camada de execução REAL exige contratos próprios e permanece desabilitada. Nenhuma das mutações auditadas cria autoridade de execução.

### 2. Aprendizagem não autoriza trading

As respostas HTTP de aprendizagem continuam explicitando `execution_allowed: false` ou `operation_eligible: false`, e o serviço mantém a regra de que conhecimento externo não concede autoridade de operação.

### 3. Integridade de aprendizagem ainda depende da fronteira de identidade

Os endpoints de validação/admissão aceitam os próprios booleanos de validação no payload. Isso não é um bypass de execução, mas é uma falsificação potencial da proveniência de conhecimento se a API for publicada para terceiros. A correção arquitetural é autenticar/autorizAR a ação de validação, não transformar o booleano em prova de confiança.

### 4. Resultado de operação precisa de identidade/escopo

`/api/outcome` consegue alterar um `decision_id` existente sem exigir identidade ou tenant. Em ambiente local de usuário único isso é funcional; em SaaS multiusuário é uma superfície de corrupção de histórico/estatísticas e precisa ser protegida antes da exposição pública.

### 5. Replay tem efeito de memória

`EcosystemService.replay()` usa `analyze()` e, portanto, grava cada cenário na memória/store. Isso é comportamento existente e coberto pelos testes, mas significa que replay não é uma operação puramente de leitura. O limite de corpo HTTP não substitui um limite explícito de quantidade de casos/custo computacional. Esse endurecimento deve ser feito sem quebrar a semântica atual de laboratório.

### 6. Auditoria de segurança é limitada e sem segredo bruto

O trilho guarda no máximo 1000 eventos em memória/SQLite, corta o path a 512 caracteres e guarda hash do identificador do cliente, não IP bruto, credencial, token ou corpo. A retenção centralizada multi-instância pertence à infraestrutura de produção.

### 7. Rate limit é por processo

O limite atual é 60 requisições por 60 segundos e no máximo 10.000 clientes rastreados. Isso é adequado como barreira local, mas não é uma proteção distribuída para múltiplas réplicas.

### 8. Cadeia de build foi endurecida

Foi adicionado `.dockerignore` para excluir `.runtime`, bancos SQLite, `.env`, logs, caches e artefatos Git/dev do contexto Docker. Isso evita copiar acidentalmente estado local ou arquivos de segredo para a imagem durante um build feito a partir de uma árvore de trabalho contaminada.

### 9. Publicação foi explicitamente classificada

`README_DEPLOY.md` agora deixa explícito que a publicação atual é para teste/uso controlado, não uma implantação SaaS multiusuário de produção. Também registra os requisitos restantes de autenticação, autorização, sessão, tenant isolation e armazenamento compartilhado.

## Não corrigir artificialmente

Não devem ser criados atalhos para habilitar REAL, nem considerar um booleano enviado pelo navegador como prova de identidade, validação de conhecimento, autorização administrativa ou propriedade de uma decisão. Essas garantias devem vir de uma fronteira de confiança real.

## Próxima correção técnica prioritária

1. Introduzir uma camada HTTP de identidade/autorização provider-neutral.
2. Vincular mutações e leituras sensíveis a `subject_id` + `tenant_id`.
3. Transformar validação/admissão de aprendizagem em operações administrativas autenticadas.
4. Vincular `/api/outcome` ao proprietário da decisão/tenant.
5. Adicionar limite explícito de quantidade/custo no replay sem alterar sua função de laboratório.
6. Substituir rate limit em memória por mecanismo compartilhado quando houver múltiplas réplicas.
7. Manter REAL bloqueado até todos os gates de produção estarem configurados e validados.
