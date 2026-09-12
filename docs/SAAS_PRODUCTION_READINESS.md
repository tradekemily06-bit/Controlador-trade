# SaaS production readiness

## Objetivo

Este documento define a fronteira entre o ecossistema tecnicamente preparado para implantação e uma implantação SaaS de produção realmente autorizada. Ele não habilita execução REAL de operações financeiras.

## Estado atual

O núcleo mantém uma postura **fail-closed**. A implantação SaaS de produção permanece **BLOQUEADA** enquanto qualquer pré-requisito operacional abaixo não estiver comprovadamente disponível.

### Pré-requisitos obrigatórios

1. **Identidade confiável**
   - Provedor de identidade externo ou serviço equivalente, com autenticação verificável.
   - Sessões, expiração, revogação e contexto de tenant devem ser verificáveis.
   - Identidade local/in-memory não é suficiente para produção.

2. **Persistência durável e isolada por tenant**
   - Banco/armazenamento durável fora do processo da aplicação.
   - Cada registro persistido deve carregar e validar seu contexto de tenant.
   - Falha ou ausência de isolamento deve bloquear operações protegidas.

3. **Transporte seguro**
   - Produção deve ser publicada somente atrás de HTTPS/TLS válido.
   - Terminação TLS, certificados, HSTS e política de proxy devem ser responsabilidade explícita da infraestrutura.
   - O aplicativo não deve interpretar cabeçalhos de proxy não confiáveis como identidade ou origem confiável.

4. **Gerenciamento de segredos**
   - Segredos devem vir de um mecanismo dedicado de secrets management da infraestrutura.
   - Nenhum segredo deve ser armazenado no repositório, imagem, fixture, teste ou log.
   - Credenciais de DEMO também devem ser tratadas como sensíveis.

5. **Auditoria durável**
   - Eventos de segurança e operações protegidas precisam sobreviver ao reinício da aplicação.
   - A auditoria deve manter contexto de tenant, identidade, request/correlation ID e resultado sem registrar segredos ou conteúdo sensível desnecessário.
   - Falha de persistência não pode virar autorização implícita.

6. **Rate limiting centralizado**
   - Limites devem funcionar de forma consistente entre múltiplas instâncias.
   - O controle local da aplicação é defesa complementar, não substituto do controle central de produção.

## Infraestrutura recomendada antes do SaaS público

- Serviço de identidade (OIDC/OAuth2 ou equivalente) com MFA quando aplicável.
- PostgreSQL ou armazenamento durável equivalente com isolamento por tenant e política de backup.
- Secret manager do provedor de infraestrutura.
- HTTPS/TLS na borda com política de proxy explícita.
- Rate limiter/WAF ou gateway centralizado.
- Logs e métricas centralizados com retenção definida.
- Backups testados e procedimento de restauração.
- Migrações versionadas e reversíveis para o armazenamento durável.
- Ambientes separados para desenvolvimento, DEMO e produção.
- Monitoramento de disponibilidade, erros, latência e eventos de segurança.

## O que NÃO deve acontecer

- Não ativar REAL para validar a infraestrutura SaaS.
- Não transformar `in-memory` em falsa persistência multi-tenant.
- Não aceitar `X-Forwarded-*` ou cabeçalhos equivalentes como prova de identidade sem uma cadeia de proxy confiável.
- Não colocar tokens, senhas, chaves privadas ou credenciais de broker no código/repositório.
- Não permitir que saúde, notícias, contexto de mercado, memória, estatísticas ou conectividade autorizem operações financeiras.
- Não considerar o SaaS pronto apenas porque o container inicia ou `/api/health` responde `ok`.

## Critério de liberação

A implantação SaaS só pode ser considerada **READY** quando os seis pré-requisitos obrigatórios estiverem comprovados no ambiente de produção e o estado de execução REAL continuar explicitamente desabilitado até existir uma revisão separada para isso.

O código já possui uma barreira provider-neutral para representar esses pré-requisitos. Este documento descreve como a infraestrutura deve satisfazê-los; ele não finge que recursos de produção existem antes de serem provisionados e verificados.
