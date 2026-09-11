# Publicação do painel web

O Controlador Trading possui um painel mobile-first servido pelo `app.py`. O serviço pode ser hospedado como uma aplicação WSGI Python.

## Segurança

- O painel permanece em modo de simulação/DEMO.
- A API de análise retorna `execution_allowed: false`.
- REAL permanece desabilitado.
- Nenhuma credencial de corretora deve ser colocada no repositório.

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

O `Dockerfile` mantém uma opção de hospedagem Docker futura e usa a variável `PORT` (7860 por padrão). Isso não é necessário para o primeiro teste.
