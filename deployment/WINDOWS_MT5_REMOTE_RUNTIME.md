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
1. Windows inicia.
2. MT5 inicia e permanece conectado à conta DEMO.
3. O Controlador inicia localmente em 127.0.0.1:8000.
4. O Cloudflare Tunnel inicia como serviço.
5. Cloudflare Access autentica o usuário antes de encaminhar o tráfego.
6. O Controlador exige a identidade confiável para mutações remotas.
7. O mesmo hostname é usado no celular e notebook.

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