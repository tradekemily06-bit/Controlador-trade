# Controlador Trading — painel nativo MT5

Este EA coloca o Controlador Trading diretamente sobre o gráfico do MetaTrader 5.

## O que aparece no gráfico
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

O EA é apenas a camada visual/controle sobre o runtime já existente em 127.0.0.1:8000.

## Instalação
1. Abra o MT5.
2. Vá em Arquivo → Abrir pasta de dados.
3. Entre em MQL5/Experts/ControladorTrading.
4. Copie ControladorTradingPanel.mq5 para essa pasta.
5. Abra o MetaEditor e compile o arquivo.
6. No MT5, vá em Ferramentas → Opções → Expert Advisors.
7. Adicione exatamente http://127.0.0.1:8000 à lista de URLs permitidos para WebRequest.
8. Abra o gráfico, por exemplo EURUSD M5.
9. Arraste ControladorTradingPanel para o gráfico.
10. Mantenha o runtime do Controlador ativo.

## Segurança
O painel trabalha inicialmente em DEMO. O botão de ciclo usa explicitamente /api/runtime/cycle, respeitando as barreiras existentes. O painel não habilita REAL nem cria autorização REAL.
A comunicação é HTTP local com o runtime já implantado. O EA não substitui o supervisor nem o app.py.
WebRequest do MQL5 exige que o endereço do servidor seja autorizado nas opções do MT5.