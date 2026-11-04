# Control Hub · prévia Streamlit

Esta é a interface Streamlit do Controlador-Trader destinada a reunir o painel operacional e os módulos Reserva Fiscal e Assistente do Ecossistema. O Figma é somente referência visual; não é o painel que será usado na operação. A aplicação Streamlit conecta-se ao runtime local do Ecossistema, que por sua vez integra as funções de MT5. A interface Streamlit é uma aplicação web e não um overlay nativo desenhado dentro do gráfico MT5.

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
- O banco e as conversas têm escopo por proprietário, mas este runtime permanece configurado para uma única identidade autorizada (`CONTROLADOR_SINGLE_USER_IDENTITY`). Isso não significa que o deployment esteja liberado para múltiplos usuários.
- Não coloque tokens ou chaves em arquivos do repositório.
- A tela REAL permanece desabilitada. A prévia não envia ordens.

## Limites conhecidos — fidelidade visual

- O JSON contém a estrutura de navegação e tokens visuais extraídos das referências.
- **As cinco imagens originais listadas no JSON (8870.jpg, 8871.jpg, 8872.jpg, 8873.jpg e 8878.jpg não estão presentes neste branch do repositório.** A árvore do GitHub foi verificada; por isso, a aplicação não consegue exibir nem comparar as capturas originais.
- A interface Streamlit é o painel de uso pretendido. As quatro áreas visuais do Figma permanecem como referência, e o Assistente do Ecossistema é acrescentado como módulo funcional próprio em MAIS / ADMIN, sem alterar o JSON ou inventar uma quinta área.
- Não modificar nem recriar as imagens ou o arquivo original do Figma. A validação visual só poderá avançar quando as cinco imagens de referência forem disponibilizadas no projeto, mantendo os arquivos originais intactos.
- O Streamlit é acessado como painel web e conversa com o runtime do Ecossistema; não é desenhado nativamente sobre o gráfico MT5. A conexão funcional com MT5 deve ser validada no runtime DEMO antes do uso operacional.
- O Assistente do Ecossistema aparece como módulo próprio dentro de MAIS / ADMIN. A Reserva Fiscal permanece em Financeiro. Os demais módulos só devem ser considerados funcionais quando suas integrações forem efetivamente implementadas e validadas.


## Assistente · configuração do provedor

- O Assistente precisa de `OPENAI_API_KEY` configurada no ambiente protegido do processo do runtime. Não coloque a chave no navegador, no código, no repositório ou em mensagens.
- `OPENAI_MODEL` é opcional; o padrão atual é `gpt-4o-mini`.
- A rota autenticada `/api/assistant/status` verifica se o provedor e a biblioteca estão configurados, sem devolver a chave; não testa conectividade ou validade da credencial.
- Sem a chave ou sem a biblioteca, o Assistente falha de forma controlada e a interface informa que está indisponível.
- As perguntas e o resumo operacional filtrado são enviados à API da OpenAI para gerar respostas; a interface exibe esse aviso antes do chat.
- A prévia Streamlit mostra somente a sessão de consulta atual do Assistente; não lista conversas anteriores, títulos, histórico persistido ou controles para abrir/excluir conversas antigas.
