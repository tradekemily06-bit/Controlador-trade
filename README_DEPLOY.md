# Publicação do painel web

O Controlador Trading possui uma API/runtime em `app.py` e um painel Streamlit separado. Para o uso integrado com MT5, o Streamlit, a API e o terminal MT5 precisam permanecer no mesmo host Windows de runtime, com a API e o Streamlit vinculados somente ao loopback e publicados externamente apenas pelo caminho autenticado descrito em `deployment/WINDOWS_MT5_REMOTE_RUNTIME.md`.

## Segurança e limite operacional

- O painel permanece em modo de simulação/DEMO.
- A API de análise retorna `execution_allowed: false` quando as barreiras de execução não foram satisfeitas.
- REAL permanece desabilitado até validação específica e autorização humana explícita.
- Nenhuma credencial de corretora deve ser colocada no repositório.
- O runtime mantém exclusividade de processo sobre o diretório e os bancos SQLite configurados. Não inicie duas instâncias da API sobre os mesmos recursos.

## Hospedagem do ecossistema integrado

Para o produto operacional — painel Streamlit, API, MT5 DEMO, Assistente do Ecossistema e Reserva Fiscal — use o host Windows dedicado descrito no guia remoto. O celular e o notebook acessam o mesmo hostname HTTPS protegido por Cloudflare Access; o notebook não precisa ficar ligado quando o host remoto estiver ativo.

A API deve escutar somente em `127.0.0.1:8000`; o Streamlit deve escutar somente em `127.0.0.1:8501`. O Tunnel publica apenas o Streamlit (porta 8501). Não publique a porta 8000 diretamente na Internet. Consulte `deployment/WINDOWS_MT5_REMOTE_RUNTIME.md` para variáveis obrigatórias, identidade de usuário, supervisão e critérios de validação.

## Entrada WSGI antiga / PythonAnywhere

O arquivo `deployment/pythonanywhere_wsgi.py` é mantido apenas como entrada WSGI legada para experimentos isolados da API. **Ele não implanta o painel Streamlit integrado, não hospeda o terminal MT5 Windows e não constitui o ambiente operacional do Ecossistema Controlador Trading.**

Além disso, o runtime adquire locks de processo durante a importação de `app.py`. Plataformas WSGI que iniciam múltiplos workers iniciam processos independentes; o segundo processo que tentar compartilhar os mesmos arquivos deve falhar ao adquirir o lock. A documentação oficial do PythonAnywhere confirma que workers são processos separados e que planos pagos podem usar mais de um worker. Portanto, não use PythonAnywhere com múltiplos workers para este runtime nem tente contornar o bloqueio compartilhando os mesmos bancos. Um worker único não resolve a ausência do MT5 Windows e do painel Streamlit integrado.

Referências oficiais sobre o modelo de workers:
- https://help.pythonanywhere.com/pages/GlobalStateAndWebApps
- https://help.pythonanywhere.com/pages/HowManyHitsCanMySiteHandle/

## Alternativa Docker

O `Dockerfile` é uma opção para ambientes que não dependem de um terminal MT5 Windows local. Ele inicia `python app.py` em um único processo de API. Não confunda essa imagem isolada com a implantação integrada MT5 + Streamlit do host Windows; a validação de broker/terminal não é fornecida pelo container.
