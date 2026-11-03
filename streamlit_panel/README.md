# Control Hub · prévia Streamlit

Esta aplicação é uma interface web separada para desenvolver e validar os módulos Assistente do Ecossistema e Reserva Fiscal. Ela não modifica o arquivo original do Figma nem substitui o painel aprovado do MT5.

## Instalação local (Windows / Python 3.12)

No diretório raiz do repositório:

1. Instale as dependências:

   `py -3.12 -m pip install -r streamlit_panel/requirements.txt`

2. Inicie o runtime do Ecossistema em outro terminal, na porta configurada (padrão: 8000).

3. Inicie a prévia:

   `py -3.12 -m streamlit run streamlit_panel/app.py --server.address 127.0.0.1 --server.port 8501`

A URL local padrão será `http://127.0.0.1:8501`.

## Integração e segurança

- Por padrão, a prévia chama `http://127.0.0.1:8000`. Altere `CONTROLADOR_API_BASE_URL` somente quando o runtime estiver publicado em um endereço confiável.
- Em implantação remota, configure `CONTROLADOR_REMOTE_ACCESS_REQUIRED=true` e `CONTROLADOR_TRUSTED_IDENTITY_HEADER` no runtime e no Streamlit.
- O proxy de identidade deve remover qualquer cabeçalho de identidade enviado pelo visitante e inserir o valor autenticado. O Streamlit encaminha apenas esse cabeçalho para a API.
- Configure a identidade individual autorizada em `CONTROLADOR_SINGLE_USER_IDENTITY`. Não exponha diretamente a porta 8501 nem a porta 8000; publique somente pelo proxy/Tunnel com Cloudflare Access.
- Não coloque tokens ou chaves em arquivos do repositório.
- A tela REAL permanece desabilitada. A prévia não envia ordens.

## Limites conhecidos

- As imagens originais são referências imutáveis; o JSON reproduz a especificação de navegação e tokens visuais. As imagens contêm barras do Android/visualizador e não são usadas como tela final.
- A prévia Streamlit não é o overlay nativo do gráfico MT5. A integração visual nativa no MT5 é uma etapa distinta.
- Outros módulos aparecem como seleção, mas só Assistente e Reserva Fiscal têm chamadas funcionais conectadas nesta prévia.
