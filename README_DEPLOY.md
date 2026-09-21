# Publicação do painel web

O Controlador Trading possui um painel mobile-first servido pelo `app.py`. O serviço pode ser hospedado como uma aplicação WSGI Python.

## Segurança e limite desta publicação

- O painel permanece em modo de simulação/DEMO.
- A API de análise retorna `execution_allowed: false`.
- REAL permanece desabilitado.
- Nenhuma credencial de corretora deve ser colocada no repositório.
- A configuração atual suporta apenas um deployment SaaS público **single-instance**, com armazenamento tenant+subject-scoped e identidade confiável fornecida pela borda. Isso não equivale a suporte a SaaS horizontal/multi-instance.
- A aplicação exige uma identidade confiável injetada pela infraestrutura para as rotas protegidas, mas a autenticação/sessão em si continua sendo responsabilidade da borda/identity provider.
- Antes de escalar para múltiplas instâncias, a implantação precisa adicionar um provedor de armazenamento compartilhado que cumpra o contrato tenant-scoped e também uma solução centralizada de rate limiting. SQLite local continua explicitamente limitado a uma única instância.
- Em especial, a infraestrutura deve garantir que as chaves WSGI `controlador.trusted_*` não possam ser fornecidas pelo cliente e que somente o identity provider confiável possa injetá-las. O processo WSGI não deve ficar diretamente exposto sem essa borda.

## Hospedagem recomendada para o primeiro teste

Para um teste pelo celular, PythonAnywhere oferece uma conta Beginner gratuita com uma aplicação web em `seu-usuario.pythonanywhere.com`. O arquivo `deployment/pythonanywhere_wsgi.py` já existe para servir de entrada WSGI.

Fluxo:

1. Criar a conta gratuita.
2. Abrir um console Bash.
3. Clonar este repositório na pasta `~/Controlador-trade`.
4. Na aba Web, criar uma aplicação Python/Manual.
5. Apontar o arquivo WSGI para `~/Controlador-trade/deployment/pythonanywhere_wsgi.py`.
6. Recarregar a aplicação.
7. Abrir o endereço público fornecido pelo PythonAnywhere.

O health check fica em `/api/health`.

## Alternativa Docker

O `Dockerfile` mantém uma opção de hospedagem Docker futura e usa a variável `PORT` (7860 por padrão). O contexto de build agora exclui `.runtime`, bancos SQLite, arquivos `.env`, logs e artefatos de desenvolvimento por meio de `.dockerignore`.

Isso não configura autenticação SaaS nem habilita REAL; continua sendo apenas uma proteção de cadeia de build contra inclusão acidental de dados locais no container.
