# Control Hub · painel Streamlit

Esta é a interface Streamlit do Controlador-Trader destinada a reunir o painel operacional e os módulos Reserva Fiscal e Assistente do Ecossistema. O Figma é somente referência visual e não é alterado por esta implementação; o Streamlit é o painel de uso pretendido. A aplicação Streamlit conecta-se ao runtime do Ecossistema, que por sua vez integra as funções de MT5. A interface é uma aplicação web, não um overlay nativo desenhado dentro do gráfico MT5.

## Instalação local (Windows / Python 3.12)

No diretório raiz do repositório:

1. Instale as dependências do runtime (inclui o cliente OpenAI usado pelo Assistente):

   `py -3.12 -m pip install -r requirements.txt`

2. Instale as dependências do painel Streamlit:

   `py -3.12 -m pip install -r streamlit_panel/requirements.txt`

3. Se este computador Windows também for hospedar a conexão MT5 DEMO, instale o pacote Python do MetaTrader 5 e confirme que o terminal MT5 está instalado e em execução:

   `py -3.12 -m pip install MetaTrader5`

   Esta dependência é específica do ambiente Windows com terminal MT5; instalar o Streamlit, por si só, não instala nem conecta o terminal.

4. Inicie o runtime do Ecossistema em um primeiro PowerShell:

   `$env:CONTROLADOR_REMOTE_ACCESS_REQUIRED="false"; $env:CONTROLADOR_LOCAL_MUTATIONS_ALLOWED="true"; py -3.12 app.py`

5. Em um segundo PowerShell, na mesma pasta do projeto, inicie o painel:

   `py -3.12 -m streamlit run streamlit_panel/app.py --server.address 127.0.0.1 --server.port 8501`

A URL local padrão será `http://127.0.0.1:8501`. Mantenha os dois terminais abertos enquanto estiver usando o painel: um executa a API/runtime na porta 8000 e o outro executa a interface Streamlit na porta 8501.

A autorização local acima é somente para desenvolvimento no próprio computador. Não use essas variáveis como configuração de acesso remoto e não exponha as portas 8000 ou 8501 à internet.

## Integração e segurança

- Por padrão, o painel chama `http://127.0.0.1:8000`. Altere `CONTROLADOR_API_BASE_URL` somente quando o runtime estiver publicado em um endereço confiável.
- Em implantação remota, configure `CONTROLADOR_REMOTE_ACCESS_REQUIRED=true` e `CONTROLADOR_TRUSTED_IDENTITY_HEADER` no runtime e no Streamlit.
- O proxy de identidade deve remover qualquer cabeçalho de identidade enviado pelo visitante e inserir o valor autenticado. O Streamlit encaminha esse cabeçalho para a API.
- Configure `CONTROLADOR_SINGLE_USER_IDENTITY` com a identidade autorizada pelo Cloudflare Access. Não exponha diretamente a porta 8501 nem a porta 8000; publique somente pelo proxy/Tunnel com Cloudflare Access.
- O banco fiscal e as conversas do Assistente têm escopo por proprietário, mas este runtime permanece configurado para uma única identidade autorizada (`CONTROLADOR_SINGLE_USER_IDENTITY`). Isso não significa que o deployment esteja liberado para múltiplos usuários.
- Não coloque tokens ou chaves em arquivos do repositório.
- A tela REAL permanece desabilitada. O painel não deve ser considerado autorização para enviar ordens.

## Módulos no painel

- A Reserva Fiscal permanece em Financeiro. Categorias sem cálculo validado ficam pendentes e fora dos totais; a estimativa brasileira identificada na interface é planejamento, não apuração de imposto devido.
- O Assistente do Ecossistema é acrescentado como módulo funcional próprio em MAIS / ADMIN. A interface lista até 30 conversas salvas, permite abrir o histórico recente e excluir uma conversa somente após ação explícita do usuário.
- A pergunta, as mensagens recentes da conversa e um resumo operacional filtrado são enviados à OpenAI quando o usuário envia uma consulta. As mensagens também ficam armazenadas no histórico local do Assistente no servidor do Ecossistema. A chave OpenAI permanece no servidor; não envie senhas, códigos de acesso ou dados bancários sensíveis.
- A consulta de status do Assistente verifica a configuração local do cliente, mas não testa conectividade nem validade da chave. A conexão real não é considerada validada até um teste autorizado.
- Replay e Simulador têm limitações descritas na própria interface. O backtest atual não integra Risk Manager, margem, alavancagem, swap ou conversão para a moeda da conta. Não o trate como previsão nem como backtest financeiro completo.
- Os demais módulos só devem ser considerados operacionais quando suas integrações forem efetivamente implementadas e validadas.

## Limites conhecidos — fidelidade visual e implantação

- O JSON contém a estrutura de navegação e tokens visuais extraídos das referências.
- **As cinco imagens originais listadas no JSON (8870.jpg, 8871.jpg, 8872.jpg, 8873.jpg e 8878.jpg) não estão presentes neste branch do repositório.** Portanto, ainda não é possível fazer a comparação visual final.
- As quatro áreas visuais do Figma permanecem como referência; o Assistente é um módulo funcional próprio em MAIS / ADMIN, sem alterar o JSON ou inventar uma quinta área visual.
- Não modificar nem recriar as imagens ou o arquivo original do Figma. A validação visual só poderá avançar quando as cinco imagens originais forem disponibilizadas para comparação, mantendo os arquivos intactos.
- O Streamlit é acessado como painel web e conversa com o runtime do Ecossistema; não é desenhado nativamente sobre o gráfico MT5. A conexão funcional com MT5 deve ser validada no runtime DEMO antes do uso operacional.

## Acesso por um único link e continuidade com o notebook desligado

**Este acesso remoto ainda não está implantado nem validado.** A instalação local descrita acima depende de dois processos no computador e só fica disponível enquanto o runtime e o Streamlit estiverem em execução. Não existe, neste estado do repositório, um link público de produção pronto para uso no celular.

Para atingir o objetivo de acessar o mesmo painel pelo celular e pelo notebook sem manter o notebook pessoal ligado, a implantação precisa manter os componentes necessários em infraestrutura remota:

- Hospedar o Streamlit e o runtime/API como serviços persistentes, com comunicação privada entre eles. O painel deve apontar CONTROLADOR_API_BASE_URL para a API privada e confiável.
- O runtime escuta em 127.0.0.1 por padrão. CONTROLADOR_BIND_HOST pode alterar o endereço de escuta; só configurar 0.0.0.0 quando o serviço estiver isolado em rede privada e protegido por proxy autenticado/firewall. Nunca publicar a porta 8000 diretamente na internet.
- Proteger o acesso web e a API com o mesmo provedor de identidade confiável. O proxy precisa remover cabeçalhos de identidade fornecidos pelo visitante e inserir o cabeçalho autenticado; manter CONTROLADOR_REMOTE_ACCESS_REQUIRED=true, CONTROLADOR_TRUSTED_IDENTITY_HEADER e CONTROLADOR_SINGLE_USER_IDENTITY coerentes nos serviços.
- Manter armazenamento persistente e backups protegidos para .runtime, banco fiscal e histórico do Assistente. Não usar armazenamento efêmero para esses dados.
- Se as operações MT5 precisarem continuar enquanto o notebook pessoal estiver desligado, o terminal MT5 e o adaptador DEMO também precisam executar em uma máquina Windows/VPS continuamente ligada e validada. Hospedar somente o Streamlit não mantém o MT5 conectado.
- Validar saúde, autenticação, isolamento de identidade, persistência após reinício, conectividade MT5 DEMO e bloqueio REAL antes de liberar o link para uso.

Não foi feita implantação, não foram criadas credenciais, não foi aberto acesso público e nenhuma ordem foi enviada. A escolha do provedor e a configuração de produção permanecem pendentes.

## Integração funcional dentro do gráfico MT5

O repositório também contém a interface nativa do MT5 em `mql5/Experts/ControladorTrading/Controlador-Trading.mq5`. Ela é um Expert Advisor (EA) que desenha controles reais no gráfico com objetos MQL5, trata cliques em `OnChartEvent`, atualiza dados por `OnTimer` e consulta o runtime por HTTP usando `WebRequest`. Portanto, a interface do MT5 não é uma imagem estática.

A arquitetura tem dois clientes ligados ao mesmo runtime:
- **MT5:** o EA MQL5 é a camada nativa que fica dentro do gráfico e apresenta controles e dados operacionais.
- **Streamlit:** é a interface web complementar para as áreas do Ecossistema, incluindo Reserva Fiscal e Assistente, conectada à mesma API/runtime.

**Limite importante:** o Streamlit não é executado dentro do gráfico MT5 e não deve ser descrito como se fosse. A camada que aparece dentro do gráfico é o EA MQL5. As duas interfaces só podem ser consideradas integradas ponta a ponta depois de validar que consultam e atualizam o mesmo estado do runtime, com autenticação e permissões seguras. O EA atualmente usa por padrão `http://127.0.0.1:8000`; esse endereço local exige que o runtime esteja ativo no mesmo computador. Para uso remoto, a arquitetura precisa ser adaptada com segurança, sem expor a API diretamente.
