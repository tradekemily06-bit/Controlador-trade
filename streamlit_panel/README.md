# Control Hub · prévia Streamlit

Esta aplicação é uma interface web separada para desenvolver e validar os módulos Assistente do Ecossistema e Reserva Fiscal. Ela não modifica o arquivo original do Figma nem substitui o painel aprovado do MT5.

## Instalação local (Windows / Python 3.12)

No diretório raiz do repositório:

1. Instale as dependências:

   `py -3.12 -m pip install -r streamlit_panel/requirements.txt`

2. Inicie o runtime do Ecossistema em um primeiro PowerShell. A API exige uma autorização local explícita para as rotas do Assistente e da Reserva Fiscal; sem estas variáveis, essas telas responderão com acesso negado. Execute:

   `$env:CONTROLADOR_REMOTE_ACCESS_REQUIRED="false"; $env:CONTROLADOR_LOCAL_MUTATIONS_ALLOWED="true"; py -3.12 app.py`

3. Em um segundo PowerShell, na mesma pasta do projeto, inicie a prévia:

   `py -3.12 -m streamlit run streamlit_panel/app.py --server.address 127.0.0.1 --server.port 8501`

A URL local padrão será `http://127.0.0.1:8501`. Mantenha os dois terminais abertos enquanto estiver usando a prévia.

A autorização local acima é somente para desenvolvimento no próprio computador. Não use essas variáveis como configuração de acesso remoto e não exponha as portas 8000 ou 8501 à internet.

## Integração e segurança

- Por padrão, a prévia chama `http://127.0.0.1:8000`. Altere `CONTROLADOR_API_BASE_URL` somente quando o runtime estiver publicado em um endereço confiável.
- Em implantação remota, configure `CONTROLADOR_REMOTE_ACCESS_REQUIRED=true` e `CONTROLADOR_TRUSTED_IDENTITY_HEADER` no runtime e no Streamlit.
- O proxy de identidade deve remover qualquer cabeçalho de identidade enviado pelo visitante e inserir o valor autenticado. O Streamlit encaminha apenas esse cabeçalho para a API.
- Configure a identidade individual autorizada em `CONTROLADOR_SINGLE_USER_IDENTITY`. Não exponha diretamente a porta 8501 nem a porta 8000; publique somente pelo proxy/Tunnel com Cloudflare Access.
- Até existir isolamento fiscal por proprietário, mantenha somente uma identidade individual autorizada para acessar o runtime remoto.
- Não coloque tokens ou chaves em arquivos do repositório.
- A tela REAL permanece desabilitada. A prévia não envia ordens.

## Limites conhecidos

- As imagens originais são referências imutáveis; o JSON reproduz a especificação de navegação e tokens visuais. As imagens contêm barras do Android/visualizador e não são usadas como tela final.
- A prévia Streamlit não é o overlay nativo do gráfico MT5. A integração visual nativa no MT5 é uma etapa distinta.
- Outros módulos aparecem como seleção, mas só Assistente e Reserva Fiscal têm chamadas funcionais conectadas nesta prévia.
