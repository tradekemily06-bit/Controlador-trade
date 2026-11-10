# Windows MT5 remote runtime

Este é o desenho de uso diário do Controlador Trading: um único runtime Windows hospeda o Controlador e o terminal MT5 DEMO. Celular e notebook acessam o mesmo hostname HTTPS.

## Componentes
- Windows Server/VPS
- terminal MetaTrader 5 conectado à conta IC Markets DEMO
- Python + dependências do projeto
- pacote MetaTrader5 de requirements-mt5.txt
- Controlador Trading (API/MT5) ouvindo somente em 127.0.0.1:8000, sem rota pública direta
- Painel Streamlit ouvindo somente em 127.0.0.1:8501 e chamando a API pela interface loopback
- Cloudflare Tunnel como transporte HTTPS sem porta inbound pública, com o hostname do painel roteado para `http://127.0.0.1:8501`
- Cloudflare Access protegendo o hostname do painel e inserindo a identidade confiável; a porta 8000 não deve ser publicada no Tunnel

## Variáveis obrigatórias do runtime remoto

CONTROLADOR_BIND_HOST=127.0.0.1
PORT=8000
CONTROLADOR_EXECUTION_PROVIDER=ic_markets_mt5_demo
CONTROLADOR_REMOTE_ACCESS_REQUIRED=true
CONTROLADOR_LOCAL_MUTATIONS_ALLOWED=true
CONTROLADOR_LOCAL_MUTATION_HOSTS=localhost,127.0.0.1,[::1]
CONTROLADOR_TRUSTED_IDENTITY_HEADER=Cf-Access-Authenticated-User-Email
CONTROLADOR_SINGLE_USER_IDENTITY=usuario-individual-autorizado@example.com

`CONTROLADOR_SINGLE_USER_IDENTITY` é uma configuração local obrigatória: defina-a no escopo de Máquina do Windows com o e-mail individual exato permitido na política Cloudflare Access, antes de instalar as tarefas agendadas. Não use domínio inteiro, grupo ou identidade compartilhada. O bootstrap não cria esse valor automaticamente e o instalador recusa registrar as tarefas quando ele está ausente. Não grave tokens ou senhas nesse valor.
CONTROLADOR_RUNTIME_DIR=C:\\Controlador-trade\\.runtime
CONTROLADOR_SECURITY_AUDIT_DB=C:\\Controlador-trade\\.runtime\\security-audit.sqlite

### Configuração mínima do Tunnel gerenciado localmente

Use uma rota de hostname para o Streamlit e exija que o próprio `cloudflared` valide o JWT do Access antes de encaminhar ao origin. Substitua os três valores entre sinais de menor/maior pelos dados da sua conta e aplicação Access; não copie valores fictícios para produção.

```yaml
ingress:
  - hostname: painel.seu-dominio.example
    service: http://127.0.0.1:8501
    originRequest:
      access:
        required: true
        teamName: <seu-team-name>
        audTag:
          - <aud-tag-da-aplicacao-access>
  - service: http_status:404
```

Não crie uma segunda rota pública para `127.0.0.1:8000`. A API é chamada pelo Streamlit localmente. O `Cf-Access-Authenticated-User-Email` usado pela aplicação identifica o usuário, mas não é uma assinatura criptográfica: a barreira de autenticidade da borda é a validação do JWT `Cf-Access-Jwt-Assertion` pelo `cloudflared` com `required: true`, além da origem inacessível diretamente. Se a aplicação for movida para fora desse caminho protegido por Tunnel, a API/origin deverá validar assinatura, emissor e audiência do JWT antes de confiar na identidade. Não substitua essa validação por simples decodificação do token.

## Assistente do Ecossistema

Para habilitar respostas com IA, configure `OPENAI_API_KEY` como variável de ambiente protegida no usuário/serviço Windows que inicia o runtime. A chave fica somente no servidor; nunca a coloque no Git, na interface web, em arquivos servidos ao navegador ou em mensagens do Assistente. Opcionalmente, configure `OPENAI_MODEL`; sem essa variável, o serviço usa o modelo padrão definido pelo código. Sem `OPENAI_API_KEY`, a rota de conversa responde como indisponível e não deve ser tratada como Assistente operacionalmente pronto.

O texto da pergunta e o resumo operacional enviado ao provedor externo devem ser informados ao usuário na interface. Não envie senhas, tokens, códigos de autenticação ou dados bancários sensíveis. O Assistente permanece somente leitura e recebe agregados da Reserva Fiscal, não o histórico individual de referências e observações. A exclusão de uma conversa pela interface apaga a conversa e suas mensagens do banco local do Ecossistema, mas não solicita nem garante exclusão de dados já transmitidos ao provedor externo; a retenção do provedor segue as configurações e políticas da conta/API. Não prometa ao usuário exclusão externa.

CONTROLADOR_UPDATE_TOKEN continua sendo segredo de ambiente quando o endpoint interno de atualizações for usado.

## Ordem de inicialização
1. Windows inicia e entra na sessão dedicada do runtime.
2. O agendador inicia o MT5.
3. O launcher do Controlador faz preflight somente leitura e aguarda o MT5 DEMO por uma janela limitada.
4. O Controlador inicia localmente em 127.0.0.1:8000; se o MT5 ainda estiver indisponível, ele continua bloqueado para execução até o runtime ficar válido.
5. O Cloudflare Tunnel inicia como serviço.
6. Cloudflare Access autentica o usuário antes de encaminhar o tráfego.
7. O Controlador exige a identidade confiável para mutações remotas.
8. O mesmo hostname é usado no celular e notebook.

A inicialização do runtime **não sincroniza, substitui nem compila o EA MQL5 instalado**. Atualizações do EA são manutenção separada: exigem execução explícita de `deployment/sync_mql5_panel.ps1`, revisão do artefato e validação em DEMO. O instalador de tarefas agendadas não instala nem chama esse utilitário.

## Supervisão e recuperação contínua

Os launchers de MT5, Controlador e Streamlit atuam como supervisores do processo, além do início automático do host. O supervisor do Streamlit também mantém o processo vivo: ao atingir o orçamento móvel de reinícios por hora, permanece em `RECOVERING`, aguarda a tentativa mais antiga sair da janela de uma hora e retoma automaticamente. Esse orçamento limita a frequência de tentativas, não encerra o painel nem define prazo de uso. O runtime não tem prazo de expiração nem encerra o supervisor ao atingir o orçamento de reinícios. Se um processo cair, o supervisor registra o evento, aplica um atraso de recuperação e tenta reiniciar dentro de um orçamento móvel de reinícios por hora (o Controlador usa 6/h por padrão). Ao atingir o orçamento, permanece ativo em estado `RECOVERING`, aguarda até que a tentativa mais antiga saia da janela móvel de uma hora e então retoma as tentativas automaticamente. Esse limite regula a frequência de reinícios, não o tempo total de disponibilidade, e evita loops agressivos em falhas persistentes. Falhas que não provem estado DEMO seguro e ausência de posições/ordens continuam bloqueadas e podem exigir intervenção humana.

O Agendador de Tarefas também recebe uma política de reinício para falha da própria tarefa. Isso cria duas camadas complementares: recuperação do processo pelo supervisor e recuperação do host da tarefa pelo Windows.

A supervisão não autoriza execução. No supervisor do MT5, o health contínuo verifica conexão real do terminal e conta DEMO; disponibilidade de cotação/símbolo é tratada separadamente como condição de mercado/dados. Assim, fechamento de mercado ou ausência temporária de tick não deve ser confundido com terminal morto nem provocar reinício desnecessário do MT5. Antes de cada nova inicialização do Controlador, o preflight DEMO é repetido; se o MT5 não estiver seguro, o Controlador pode iniciar para manter a interface/observabilidade, mas a execução continua sujeita aos gates existentes e permanece bloqueada quando qualquer pré-requisito estiver inseguro.

O supervisor do Controlador separa dois tipos de verificação:
- `/api/health/live` é uma verificação leve de que o processo HTTP está respondendo. Ela não consulta corretora, banco, risco ou observabilidade e é usada para decidir se o processo precisa de reinício.
- `/api/health` continua sendo o diagnóstico detalhado de segurança e operação. Se esse diagnóstico ficar lento, indisponível ou apontar atenção, o supervisor marca `ATTENTION` e mantém a execução bloqueada; não mata um processo que ainda responde ao liveness só porque o diagnóstico detalhado demorou.

Somente a falha persistente do liveness pode acionar a recuperação do processo. A resposta de liveness nunca concede permissão de execução nem declara a conta DEMO saudável.

Antes de uma recuperação automática, os supervisores consultam a política comum `core/self_repair_policy.py` por meio de `deployment/authorize_self_repair.py`. O início do terminal configurado é limitado e não concede autorização para operar. Reinícios do Controlador/MT5 só são autorizados quando uma verificação independente confirma conta DEMO, posições/ordens consultáveis e vazias, orçamento de tentativas disponível, cooldown concluído e ausência de `.runtime/maintenance.lock`. Qualquer estado desconhecido bloqueia o reinício e registra `ATTENTION` para intervenção humana. A autorização não executa ordens nem altera permissões REAL.

O supervisor do MT5 não encerra automaticamente um terminal quando a conta não pode ser confirmada como DEMO, quando não é possível verificar posições/ordens, ou quando existem posições/ordens abertas. Nesses casos, registra a razão e exige supervisão humana. Uma parada controlada explicitamente solicitada é tratada separadamente, mas ainda exige confirmação de conta DEMO.

Cada supervisor grava um estado pequeno e não secreto em `CONTROLADOR_RUNTIME_DIR`:
- `controlador-supervisor-status.json`
- `mt5-supervisor-status.json`

Esses estados são somente telemetria. Falhas ou recuperação em andamento são incorporadas à observabilidade operacional e ao centro de notificações; nunca concedem autoridade de execução.

Para manutenção controlada, o runtime usa marcadores locais de parada do supervisor. A remoção/uso desses marcadores pertence ao mecanismo de gerenciamento do runtime e não exige que o usuário execute comandos diariamente.

## Inicialização automática no Windows
O instalador exige uma execução única como Administrador e oferece dois modos:

- `Interactive` (padrão): inicia no logon do usuário dedicado. É apropriado para validação inicial, mas **não é uma garantia de 24/7 após logoff/reboot sem logon**.
- `AtStartupS4U`: inicia no boot sem depender de uma sessão interativa. É o modo destinado ao host 24/7; antes de produção, o MT5 precisa ser validado nesse tipo de sessão, porque o repositório não pode assumir que o terminal do broker funcionará sem desktop interativo.

Exemplo do modo 24/7: `-AutostartMode AtStartupS4U`. A configuração é feita uma vez; durante o uso diário não há necessidade de executar Git ou Python manualmente.

O instalador não grava senha, token ou segredo. O Controlador continua fazendo preflight DEMO e não transforma uma falha do MT5 em autorização: sem DEMO válido, a execução permanece bloqueada.

## Serviço persistente do Cloudflare Tunnel — etapa separada

O instalador `install_windows_autostart.ps1` registra somente as três tarefas agendadas do MT5, Controlador e Streamlit. Ele **não instala nem registra o serviço Windows `cloudflared`** e não cria a conta, o túnel, o DNS, o hostname ou a aplicação Cloudflare Access. Portanto, instalar as tarefas do ecossistema, isoladamente, não conclui o acesso remoto 24/7.

No host Windows permanente, crie/configure o Tunnel no painel Cloudflare, publique exclusivamente o hostname do Streamlit em `http://127.0.0.1:8501`, configure a validação obrigatória do Access na borda e instale o conector como serviço Windows usando o comando oficial `cloudflared.exe service install <TUNNEL_TOKEN>` em terminal elevado. O token é segredo: não o coloque no Git, em scripts versionados, logs, prints ou mensagens. Confirme no Windows que o serviço `cloudflared` está em execução e no painel Cloudflare que o Tunnel está `Healthy`. A porta 8000 permanece privada.

A documentação oficial recomenda executar o Tunnel como serviço para iniciar no boot e continuar ativo enquanto o origin estiver online: https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/as-a-service/ e https://developers.cloudflare.com/tunnel/get-started/. A instalação do serviço não substitui a validação de rota, Access, hostname e health do painel.
## Proteção Cloudflare Access
A rota publicada deve estar protegida por uma aplicação Cloudflare Access e o Tunnel deve exigir a validação do Access antes de encaminhar o tráfego ao origin. Para túnel gerenciado localmente, isso corresponde a `originRequest.access.required: true` com o `teamName` e o `audTag` da aplicação; em túnel gerenciado remotamente, configure a mesma exigência nas opções da rota. Assim, o header de identidade usado pelo Controlador chega somente depois da autenticação/validação na borda.

O origin da API continua em `http://127.0.0.1:8000` e o origin web do Streamlit é `http://127.0.0.1:8501`. O hostname HTTPS do painel deve apontar para a porta 8501, protegido por Cloudflare Access; a porta 8000 permanece privada e não deve ser publicada como hostname/rota pública. O Streamlit encaminha o cabeçalho de identidade recebido do proxy para a API, que compara a identidade com `CONTROLADOR_SINGLE_USER_IDENTITY`. As rotas remotas de mutação continuam exigindo o cabeçalho de identidade confiável do Cloudflare Access. Há uma exceção estreita para o EA nativo no mesmo host: os endpoints `/api/runtime/*/local`, `/api/fiscal-reserve/local`, `/api/assistant/local/status` e `/api/assistant/local/chat` exigem simultaneamente `CONTROLADOR_LOCAL_MUTATIONS_ALLOWED=true`, cliente loopback (`127.0.0.1` ou `::1`) e Host na allowlist `CONTROLADOR_LOCAL_MUTATION_HOSTS`. As rotas fiscais nativas são somente leitura; o chat nativo exige `consent_to_openai=true` explicitamente em cada envio e usa a identidade proprietária configurada no servidor. O EA não pode escolher `owner_id` nem fornecer identidade confiável. O runtime não confia em cabeçalho de identidade fornecido pelo próprio EA. Além do loopback e da allowlist de Host, a rota local rejeita qualquer requisição que carregue o cabeçalho de identidade confiável configurado para o Cloudflare Access; isso protege também contra um túnel/reverse proxy que conecte ao origin por loopback. A implantação ainda precisa confirmar que o Cloudflare Access encaminha esse cabeçalho ao origin; notebook/celular devem usar exclusivamente o hostname HTTPS protegido.

## Regras de segurança
- REAL não é habilitado por padrão; quando necessário, usa o fluxo REAL controlado e separado, com autorização, auditoria, admission, safety gate e confirmação humana.
- O Controlador não deve escutar em endereço público.
- Não colocar senha da corretora, token Cloudflare ou segredo de atualização no Git.
- Não confiar em REMOTE_ADDR para autenticação quando houver proxy local.
- Access deve estar configurado antes da rota pública do Tunnel.
- O origin deve continuar inacessível diretamente pela Internet.
- A validação física DEMO deve ser repetida no Windows remoto antes de liberar o uso diário.

## Critério de pronto
- `/_stcore/health` responder pelo hostname HTTPS (health do Streamlit); `/api/health` deve ser verificado localmente no host em `http://127.0.0.1:8000/api/health`, pois a API 8000 não é publicada no Tunnel.
- /api/status e `/api/runtime/real/status` devem refletir o estado real do runtime; ausência de pré-requisitos mantém REAL bloqueado.
- login/identidade do Access validado.
- tarefa Windows do Streamlit ativa e `http://127.0.0.1:8501/_stcore/health` saudável no host
- hostname HTTPS do painel roteado à porta 8501 com Cloudflare Access; porta 8000 não publicada
- GET funcionar no celular e notebook.
- uma preferência alterada em um dispositivo aparecer no outro.
- o estado sobreviver a reinício.
- MT5 DEMO conectado no mesmo Windows.
- um ciclo DEMO controlado executado e reconciliado.
- não restar posição Controlador após a validação.
- falha de MT5/auth bloquear execução.
- nenhum comando de Git/Python ser necessário durante o uso diário.

## Importante
A configuração de Cloudflare exige conta/domínio e um servidor Windows real. Essas partes externas não podem ser declaradas como concluídas pelo repositório sozinho.

A opção `AtStartupS4U` remove a dependência do logon interativo do usuário para iniciar os supervisores, mas isso não prova sozinho que o MT5 estará operacional em todos os hosts. A prova final de implantação exige reboot/logoff controlado no host escolhido, confirmação de que o MT5 realmente inicializou, preflight DEMO válido, `/api/health` 2xx e recuperação após uma falha simulada.
## REAL — ativação explícita e controlada

A ponte REAL usa o mesmo terminal MT5 Windows, mas não transforma o runtime em REAL apenas por selecionar um provider. O envio REAL exige, simultaneamente:

- CONTROLADOR_EXECUTION_PROVIDER=ic_markets_mt5_real apenas no ambiente de produção;
- CONTROLADOR_REAL_AUTHORIZATION_ID e CONTROLADOR_REAL_AUDIT_ID definidos;
- CONTROLADOR_REAL_ADMISSION_ID definido;
- CONTROLADOR_REAL_EXPLICITLY_ENABLED=true;
- CONTROLADOR_REAL_EXECUTION_ALLOWED=true;
- CONTROLADOR_REAL_AUDIT_VERIFIED=true;
- CONTROLADOR_REAL_RISK_APPROVED=true;
- terminal MT5 classificado pelo próprio MetaTrader5 como conta REAL;
- mercado saudável, recovery seguro, kill switch liberado e adapter disponível;
- confirmação humana única, curta e vinculada exatamente ao request.

Essas variáveis são configuração de ambiente/segredo operacional e não devem ser gravadas no GitHub. Ausência de qualquer pré-requisito mantém o REAL bloqueado. A preparação (/api/runtime/real/prepare) não envia ordem; somente /api/runtime/real/confirm, após a confirmação humana válida, pode alcançar o RealExecutionGateway. Um resultado externo incerto não é reenviado automaticamente: exige reconciliação explícita.

## Continuidade e migração do runtime

O diretório `CONTROLADOR_RUNTIME_DIR` é o estado portátil do ecossistema. A partir desta versão, a memória de decisões usa por padrão `decision-memory.sqlite` dentro desse diretório, portanto não depende de configuração manual de um caminho externo.

Os artefatos de estado portáveis são:
- `operation-memory.json`
- `operational-safety.json`
- `execution-ledger.json`
- `execution-lifecycle.json`
- `automation-lifecycle.json`
- `runtime-checkpoint.json`
- `ecosystem-state.sqlite`
- `decision-memory.sqlite`
- `security-audit.sqlite`

`deployment/backup_runtime.ps1` cria um pacote verificado desses artefatos. O backup inclui também o lifecycle persistente da automação; usa a API de backup do SQLite para os bancos e registra SHA-256 no manifesto; segredos, tokens, senhas e configuração específica da máquina ficam fora do pacote. A restauração usa `deployment/restore_runtime.ps1`, valida o manifesto e não sobrescreve estado existente por padrão.

Assim, a troca de Windows/VPS preserva o estado do ecossistema sem transportar a identidade da máquina. O novo host deve fornecer novamente sua configuração local, MT5, Cloudflare/Access e segredos pelo mecanismo de implantação apropriado.

A escolha DEMO/REAL continua sendo uma decisão operacional separada da portabilidade. O painel pode apresentar o fluxo REAL controlado, mas a seleção ou preparação nunca substitui as barreiras de autorização, segurança, risco, recovery e confirmação humana.

## Política de identidade e isolamento dos dados fiscais

O ledger, as configurações e as filas de pendências/revisões da Reserva Fiscal usam `owner_id` nas operações de leitura e escrita. A migração verifica a identidade já gravada, as chaves únicas compostas e as relações entre filas e revisões; se encontrar proprietário incompatível, registros sem proprietário ou esquema inconsistente, bloqueia o acesso em vez de reatribuir dados. O Assistente também filtra conversas e histórico por proprietário no banco.

Apesar desse isolamento no código, esta implantação continua configurada como usuário único: `CONTROLADOR_SINGLE_USER_IDENTITY` fixa uma única identidade autorizada, e a política Cloudflare Access deve permitir somente essa identidade individual. Não use regras amplas por domínio de e-mail, organização ou grupo. Não habilite uma segunda identidade apenas por alterar a política Access: multiusuário exige uma revisão própria de tenancy, configuração, autorização, migração e testes de acesso cruzado em ambiente implantado.

O código confia no header de identidade configurado e não valida criptograficamente o JWT do Cloudflare Access. Portanto, o origin deve permanecer acessível somente pelo Tunnel/proxy confiável; o proxy deve validar o JWT na borda e sobrescrever/remover qualquer header de identidade enviado pelo cliente. Nunca publique a porta 8000 nem encaminhe tráfego direto ao origin. Se a aplicação sair dessa topologia, a própria fronteira de entrada deverá validar assinatura, emissor e audiência do JWT antes de confiar na identidade.

## Revisão profissional de pendências fiscais

A fila estrangeira oferece consulta e inclusão de evidências de revisão por item:

- `GET /api/fiscal-reserve/pending/{pending_id}/reviews`: lista o histórico de revisões.
- `POST /api/fiscal-reserve/pending/{pending_id}/reviews`: registra uma revisão com classificação sugerida, jurisdição indicada pelo profissional, nome e qualificação, identificação/registro profissional, data, referência de evidência e observações.

As duas rotas passam pela mesma autorização de identidade exigida para as demais rotas `/api/fiscal-reserve`. O registro é histórico e não altera o status `PENDING_CLASSIFICATION`, não libera alíquota e não calcula imposto ou reserva. Os campos preenchidos são declarações/documentos informados por quem usa a interface; o software não verifica a autenticidade do profissional, do registro ou do parecer. A validação efetiva deve ocorrer fora do sistema com o profissional responsável. Não use dados fictícios como parecer real.