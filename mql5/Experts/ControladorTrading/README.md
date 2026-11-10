# Controlador Trading — painel nativo MT5

Este EA coloca o Controlador Trading diretamente sobre o gráfico do MetaTrader 5.

## O que aparece no gráfico
- navegação nativa para Reserva Fiscal (resumo somente leitura) e Assistente do Ecossistema;
- Reserva Fiscal consulta o resumo do runtime, mantendo filas brasileira e estrangeira separadas e pendências fora dos totais;
- Assistente do Ecossistema permite enviar pergunta com consentimento explícito por mensagem, preservando o identificador da conversa no terminal;
- estado do runtime e HTTP;
- modo DEMO/SIMULAÇÃO;
- sinal COMPRA/VENDA/AGUARDAR;
- score;
- razão da decisão;
- ativo e timeframe configuráveis;
- botão RODAR CICLO DEMO;
- botão SALVAR CONFIGURAÇÕES;
- ciclo/external_id da execução DEMO;
- botão FECHAR DEMO + RECONCILIAR;
- preço atual do símbolo;
- estado REAL bloqueado.

O EA é a camada visual/controle sobre o runtime já existente em 127.0.0.1:8000. A Reserva Fiscal no gráfico é um resumo de consulta; os formulários, revisões documentais e histórico paginado completos continuam no Streamlit. O Assistente nativo envia a pergunta e o contexto operacional filtrado ao servidor/OpenAI somente após o clique explícito em CONSENTIMENTO OPENAI para cada envio; o histórico completo continua armazenado no servidor e acessível pelo Streamlit.

## Instalação
1. Abra o MT5.
2. Vá em Arquivo → Abrir pasta de dados.
3. Entre em MQL5/Experts/ControladorTrading.
4. Copie Controlador-Trading.mq5 para essa pasta.
5. Abra o MetaEditor e compile o arquivo.
6. No MT5, vá em Ferramentas → Opções → Expert Advisors.
7. Adicione exatamente http://127.0.0.1:8000 à lista de URLs permitidos para WebRequest.
8. Abra o gráfico, por exemplo EURUSD M5.
9. Arraste Controlador-Trading para o gráfico.
10. Mantenha o runtime do Controlador ativo.

## Segurança
As rotas nativas `/api/fiscal-reserve/local`, `/api/assistant/local/status` e `/api/assistant/local/chat` aceitam somente loopback e Host permitido, exigem `CONTROLADOR_LOCAL_MUTATIONS_ALLOWED=true` e rejeitam o cabeçalho confiável do Cloudflare quando ele estiver presente. Não publique a porta 8000 na internet. O EA não envia nem inventa identidade confiável: o runtime resolve o proprietário por configuração local. O consentimento da interface não substitui a autorização local do servidor.
O painel trabalha inicialmente em DEMO. O botão de ciclo usa explicitamente /api/runtime/cycle, respeitando as barreiras existentes. O painel não habilita REAL nem cria autorização REAL.
A comunicação é HTTP local com o runtime já implantado. O EA não substitui o supervisor nem o app.py.
WebRequest do MQL5 exige que o endereço do servidor seja autorizado nas opções do MT5.