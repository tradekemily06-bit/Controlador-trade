# Windows MT5 remote runtime

Este é o desenho de uso diário do Controlador Trading: um único runtime Windows hospeda o Controlador e o terminal MT5 DEMO. Celular e notebook acessam o mesmo hostname HTTPS.

## Componentes
- Windows Server/VPS
- terminal MetaTrader 5 conectado à conta IC Markets DEMO
- Python + dependências do projeto
- pacote MetaTrader5 de requirements-mt5.txt
- Controlador Trading ouvindo somente em 127.0.0.1:8000
- Cloudflare Tunnel como transporte HTTPS sem porta inbound pública
- Cloudflare Access como identidade na frente do hostname

## Variáveis obrigatórias do runtime remoto

CONTROLADOR_BIND_HOST=127.0.0.1
PORT=8000
CONTROLADOR_EXECUTION_PROVIDER=ic_markets_mt5_demo
CONTROLADOR_REMOTE_ACCESS_REQUIRED=true
CONTROLADOR_LOCAL_MUTATIONS_ALLOWED=true
CONTROLADOR_LOCAL_MUTATION_HOSTS=localhost,127.0.0.1,[::1]
CONTROLADOR_TRUSTED_IDENTITY_HEADER=Cf-Access-Authenticated-User-Email
CONTROLADOR_RUNTIME_DIR=C:\\Controlador-trade\\.runtime
CONTROLADOR_SECURITY_AUDIT_DB=C:\\Controlador-trade\\.runtime\\security-audit.sqlite

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

## Supervisão e recuperação contínua

Os launchers de MT5 e Controlador atuam como supervisores do processo, além do início no logon. Se um processo cair, o supervisor registra o evento, aplica um atraso de recuperação e tenta reiniciar dentro de um orçamento limitado de reinícios por hora. O limite evita loops agressivos em caso de falha persistente.

O Agendador de Tarefas também recebe uma política de reinício para falha da própria tarefa. Isso cria duas camadas complementares: recuperação do processo pelo supervisor e recuperação do host da tarefa pelo Windows.

A supervisão não autoriza execução. Antes de cada nova inicialização do Controlador, o preflight DEMO é repetido; se o MT5 não estiver seguro, o Controlador pode iniciar para manter a interface/observabilidade, mas a execução continua sujeita aos gates existentes e permanece bloqueada quando qualquer pré-requisito estiver inseguro.

Cada supervisor grava um estado pequeno e não secreto em `CONTROLADOR_RUNTIME_DIR`:
- `controlador-supervisor-status.json`
- `mt5-supervisor-status.json`

Esses estados são somente telemetria. Falhas ou recuperação em andamento são incorporadas à observabilidade operacional e ao centro de notificações; nunca concedem autoridade de execução.

Para manutenção controlada, o runtime usa marcadores locais de parada do supervisor. A remoção/uso desses marcadores pertence ao mecanismo de gerenciamento do runtime e não exige que o usuário execute comandos diariamente.

## Inicialização automática no Windows
Os scripts `deployment/install_windows_autostart.ps1`, `deployment/start_mt5_runtime.ps1` e `deployment/start_controlador_runtime.ps1` configuram o início automático no logon da sessão Windows usada pelo runtime. Essa configuração é feita uma vez; durante o uso diário não há necessidade de executar Git ou Python manualmente.

O instalador exige uma execução única como Administrador e pede apenas o caminho do executável do MT5. Nenhum segredo é gravado. O Controlador espera o preflight DEMO, mas não transforma uma falha de MT5 em autorização: sem DEMO válido, a execução continua bloqueada.

## Proteção Cloudflare Access
A rota publicada deve estar protegida por uma aplicação Cloudflare Access e o Tunnel deve exigir a validação do Access antes de encaminhar o tráfego ao origin. Para túnel gerenciado localmente, isso corresponde a `originRequest.access.required: true` com o `teamName` e o `audTag` da aplicação; em túnel gerenciado remotamente, configure a mesma exigência nas opções da rota. Assim, o header de identidade usado pelo Controlador chega somente depois da autenticação/validação na borda.

O origin continua em `http://127.0.0.1:8000`; não é necessário expor a porta 8000 na Internet. O uso direto no notebook é permitido para mutações somente quando a origem é loopback e o Host é um dos Hosts locais configurados; acessos pelo hostname público continuam exigindo a identidade confiável do Cloudflare Access.

## Regras de segurança
- REAL não é habilitado por padrão; quando necessário, usa o fluxo REAL controlado e separado, com autorização, auditoria, admission, safety gate e confirmação humana.
- O Controlador não deve escutar em endereço público.
- Não colocar senha da corretora, token Cloudflare ou segredo de atualização no Git.
- Não confiar em REMOTE_ADDR para autenticação quando houver proxy local.
- Access deve estar configurado antes da rota pública do Tunnel.
- O origin deve continuar inacessível diretamente pela Internet.
- A validação física DEMO deve ser repetida no Windows remoto antes de liberar o uso diário.

## Critério de pronto
- /api/health responder pelo hostname HTTPS.
- /api/status e `/api/runtime/real/status` devem refletir o estado real do runtime; ausência de pré-requisitos mantém REAL bloqueado.
- login/identidade do Access validado.
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
