# Auditoria profunda — integridade HTTP e data plane

## Estado desta frente

A auditoria separa explicitamente o ecossistema em três camadas:

1. **Foundation/local** — estado em memória/SQLite é permitido para desenvolvimento, laboratório e demonstração.
2. **Boundary SaaS público** — identidade confiável, tenant e subject devem vir da camada de deployment; cabeçalhos enviados pelo navegador não são aceitos como prova de identidade.
3. **Production data plane** — persistência deve ser durável e escopada simultaneamente por `tenant_id` e `subject_id`.

O modo SaaS público permanece fail-closed enquanto a terceira camada não estiver disponível.

## DecisionRecord / ownership

Toda decisão persistida para produção precisa carregar `subject_id` e `tenant_id`. O serviço aceita ownership somente através de contexto confiável e propaga esse contexto por `analyze`, `replay` e `record_outcome`.

`record_outcome` rejeita alterações cujo proprietário não corresponda ao contexto confiável. O repositório de produção exige tenant + subject na fronteira do provider, valida ownership do registro e protege os campos centrais contra alteração posterior.

Um provider que devolva um registro com ownership diferente do escopo solicitado também é tratado como violação e falha fechado.

## Store local

`DecisionStore` não é o data plane SaaS. Em `CONTROLADOR_SAAS_PUBLIC`, ele não lê histórico global e rejeita gravações. Isso evita que uma falha de roteamento transforme memória/SQLite global em armazenamento de usuário.

## Replay

Replay não possui limite funcional artificial de quantidade de cenários. A proteção de recursos deve considerar custo real — tamanho de entrada, profundidade/complexidade, CPU, memória, concorrência, armazenamento e estratégia de paginação/streaming/assíncrona quando necessária.

Replay pré-valida os cenários e só persiste depois que a análise de todos os casos é concluída com sucesso.

## Limites

Números encontrados em `MAX_*`, rate limits, tamanho de payload, retenção de auditoria e limites de risco são classificados individualmente. Nenhum limite funcional de produto deve ser introduzido apenas para restringir capacidade. Limites de segurança, anti-abuso, integridade ou risco permanecem quando protegem um recurso real ou uma propriedade de segurança.

## Pendências estruturais restantes

- data plane persistente real para SaaS;
- propagação explícita da identidade confiável nos endpoints HTTP quando o data plane estiver pronto;
- armazenamento tenant/subject-scoped para preferências, notificações e dados de aprendizagem;
- validação administrativa/proveniência confiável para conhecimento externo, sem depender de booleans autoafirmados como prova criptográfica;
- rate limiting e auditoria compartilhados entre réplicas em produção;
- estratégia explícita de CSRF quando autenticação por cookie/sessão for introduzida;
- manter REAL desligado até identidade, tenant, armazenamento durável e admissão de produção estarem efetivamente prontos.

Essas pendências são de infraestrutura de produção, não justificam liberar estado global no SaaS público.
