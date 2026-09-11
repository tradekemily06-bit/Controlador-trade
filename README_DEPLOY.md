# Publicação do painel web

O Controlador Trading possui um painel mobile-first servido pelo `app.py`. O serviço aceita a variável de ambiente `PORT` e pode ser executado em um container Docker.

## Segurança

- O painel permanece em modo de simulação/DEMO.
- A API de análise retorna `execution_allowed: false`.
- REAL permanece desabilitado.
- Nenhuma credencial de corretora deve ser colocada no repositório.

## Hospedagem

O `Dockerfile` expõe a porta definida pela variável `PORT` (7860 por padrão). A hospedagem escolhida deve executar um serviço web Docker e encaminhar a porta pública para essa porta interna.

Depois do deploy, a página inicial é `/` e o health check é `/api/health`.
