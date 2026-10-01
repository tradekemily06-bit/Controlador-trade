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

## Inicialização automática no Windows
Os scripts `deployment/install_windows_autostart.ps1`, `deployment/start_mt5_runtime.ps1` e `deployment/start_controlador_runtime.ps1` configuram o início automático no logon da sessão Windows usada pelo runtime. Essa configuração é feita uma vez; durante o uso diário não há necessidade de executar Git ou Python manualmente.

O instalador exige uma execução única como Administrador e pede apenas o caminho do executável do MT5. Nenhum segredo é gravado. O Controlador espera o preflight DEMO, mas não transforma uma falha de MT5 em autorização: sem DEMO válido, a execução continua bloqueada.

## Proteção Cloudflare Access
A rota publicada deve estar protegida por uma aplicação Cloudflare Access e o Tunnel deve exigir a validação do Access antes de encaminhar o tráfego ao origin. Para túnel gerenciado localmente, isso corresponde a `originRequest.access.required: true` com o `teamName` e o `audTag` da aplicação; em túnel gerenciado remotamente, configure a mesma exigência nas opções da rota. Assim, o header de identidade usado pelo Controlador chega somente depois da autenticação/validação na borda.

O origin continua em `http://127.0.0.1:8000`; não é necessário expor a porta 8000 na Internet.

## Regras de segurança
- REAL permanece desabilitado.
- O Controlador não deve escutar em endereço público.
- Não colocar senha da corretora, token Cloudflare ou segredo de atualização no Git.
- Não confiar em REMOTE_ADDR para autenticação quando houver proxy local.
- Access deve estar configurado antes da rota pública do Tunnel.
- O origin deve continuar inacessível diretamente pela Internet.
- A validação física DEMO deve ser repetida no Windows remoto antes de liberar o uso diário.

## Critério de pronto
- /api/health responder pelo hostname HTTPS.
- /api/status confirmar DEMO e REAL desabilitado.
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