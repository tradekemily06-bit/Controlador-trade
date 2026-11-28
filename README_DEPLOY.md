# Publicação do aplicativo standalone Ecossistema

Este guia é para o serviço independente de análise do Ecossistema, iniciado por `standalone_app.py` e empacotado em `Dockerfile.standalone`. Ele não é o painel legado servido por `app.py`, não depende de EA/MT5 instalado no servidor e não altera a interface Lovable.

## Estado de segurança

- A aplicação permanece em SIMULAÇÃO/read-only.
- REAL, envio de ordens e movimentação de dinheiro permanecem desabilitados.
- O Assistente do Ecossistema não pode enviar ordens nem movimentar dinheiro.
- Não coloque credenciais, tokens, chaves privadas ou dados de conta no repositório, imagem Docker, arquivo versionado ou logs.
- Um container saudável ou `/api/health/live` respondendo não prova que exista conexão de corretora, feed oficial, worker hospedado ou entrega de notificações.

## Entrada e configuração mínima

O container standalone executa `python standalone_app.py` e escuta em `0.0.0.0:8765`. Use uma implantação com:

- uma única réplica enquanto a persistência operacional continuar em SQLite;
- volume persistente e exclusivo montado em `/var/lib/controlador` (variável `CONTROLADOR_RUNTIME_DIR`);
- HTTPS/TLS na borda, com proxy confiável explicitamente configurado;
- identidade remota verificada por middleware confiável; token compartilhado sozinho não identifica um usuário;
- gestão externa de segredos e backups fora do host, com restauração testada.

Variáveis operacionais relevantes:

- `CONTROLADOR_SINGLE_USER_IDENTITY`: identidade obrigatória para inicialização do runtime local.
- `CONTROLADOR_RUNTIME_DIR`: diretório persistente dos bancos SQLite.
- `CONTROLADOR_BIND_HOST` e `CONTROLADOR_BIND_PORT`: endereço/porta do serviço (padrão standalone: `0.0.0.0:8765`).
- `CONTROLADOR_REMOTE_ACCESS_REQUIRED=1`: exige a fronteira de autenticação remota.
- `CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE=1`: habilita a leitura das claims injetadas pelo middleware confiável.
- `CONTROLADOR_STANDALONE_ACCESS_TOKEN`: token de acesso do gateway, armazenado somente no secret manager.
- `CONTROLADOR_ALLOWED_ORIGINS`: lista explícita de origens HTTPS autorizadas para CORS.

Não publique o serviço remotamente com identidade local de demonstração ou sem a cadeia confiável de autenticação.

## Injeção de integrações

O host aceita uma factory Python confiável configurada por operador:

`CONTROLADOR_STANDALONE_RUNTIME_FACTORY=modulo:funcao`

A função deve retornar um `StandaloneRuntime` ativo e injetar somente dependências provisionadas pelo ambiente: identidade/tenant, banco compartilhado, KMS/cipher, adaptadores de mercado read-only, transportes OAuth, fontes oficiais de calendário/notícias e sinks de notificação. A factory é carregada durante o startup; nunca a selecione por payload HTTP.

Sem essa factory, o runtime padrão é intencionalmente limitado. Não inventa credenciais, conexões ou dados ao vivo. Não configure um provider como conectado apenas para fazer o health check passar.

## Construção e execução local de validação

```bash
docker build -f Dockerfile.standalone -t controlador-ecossistema:local .
docker run --rm -p 8765:8765 \
  -e CONTROLADOR_SINGLE_USER_IDENTITY=local-validation-owner \
  -v controlador-runtime:/var/lib/controlador \
  controlador-ecossistema:local
```

Esse comando serve somente para validar a inicialização local isolada. Não é uma configuração SaaS pública: não habilita identidade remota, KMS, banco compartilhado, worker hospedado, feeds oficiais ou push externo.

Health checks:

- `/api/health/live`: processo HTTP vivo.
- `/api/readiness`: componentes configurados e limitações conhecidas.

## Critérios antes de produção

A publicação multiusuário permanece bloqueada até comprovar, no ambiente real: PostgreSQL compartilhado e migrações; isolamento tenant/subject; identidade confiável; TLS/proxy; KMS e rotação de segredos; auditoria durável; rate limiting distribuído; workers supervisionados fora do processo do navegador; backups off-host e restauração; testes reais de MT5 DEMO/cTrader DEMO; fontes oficiais de calendário/notícias; Web Push em Android/iOS com o app fechado; e integração de ponta a ponta da API com a interface Lovable existente.

SQLite é somente single-host/single-runtime. Não escale horizontalmente este container com o armazenamento atual.

Consulte também:

- `docs/SAAS_PRODUCTION_READINESS.md`
- `docs/SAAS_PRODUCTION_SECURITY_BASELINE.md`
- `docs/MULTI_REPLICA_MARKET_DATA_DEPLOYMENT.md`
- `docs/IMPLEMENTATION_COMPLETION_LEDGER.md`
