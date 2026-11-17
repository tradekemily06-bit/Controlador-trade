# Control Hub React — reconstrução isolada

Esta pasta é uma frente de interface isolada. Não substitui nem altera o painel Streamlit, o runtime Python, os módulos existentes ou o EA MQL5.

## Navegação — preservar exatamente seis áreas

A navegação deve manter estes seis nomes, nesta ordem, sem agrupar áreas ou transferir módulos entre elas:

1. **CABINE DE COMANDO**
   - Operação
   - Motor de Decisão
   - Gestão de Risco
   - Notificações
   - Ambiente MT5 DEMO
   - Kill Switch

2. **ANÁLISE**
   - Análise de Mercado
   - Memória
   - Estatísticas
   - Relatórios

3. **ESTUDO**
   - Laboratório
   - Replay
   - Simulador
   - Aprendizado
   - Descobertas
   - Escola / Tutorial / Onboarding

4. **RESERVA FISCAL**
   - Reserva Fiscal

5. **ASSISTENTE DO ECOSSISTEMA**
   - Assistente do Ecossistema

6. **CENTRAL**
   - Financeiro
   - Configurações
   - Auditoria
   - Segurança
   - Conexões
   - Multi-Broker

Não mover Reserva Fiscal para CENTRAL. Não mover Assistente do Ecossistema para CABINE DE COMANDO. Não renomear, remover ou reagrupar áreas ou módulos.

## Referência visual e dimensões

- C fechado: botão circular de 64 × 64 px, 16 px da esquerda e 16 px da base; leitura do sinal/score/estado ao lado.
- C permanece no mesmo ponto e acima da janela do painel também no estado aberto.
- Painel: posição fixa à esquerda e à base, `left: 16px`, `bottom: 16px`, `width: min(34vw, 420px)`, `max-width: calc(100vw - 32px)`, `max-height: min(84vh, 460px)`.
- Cores: fundo `#080B0F`, painel `#10151B`, módulos `#161C24`, borda `#25303B`, texto `#E9EEF3`, texto secundário `#7F8B97`, destaque `#46D6AD`.
- Cabeçalho: `Controlador-Trader` e selo `DEMO`.
- Rodapé: Estado do sistema, Alavancagem e REAL — DESABILITADO.
- Sinal e score permanecem indisponíveis nesta casca visual até conexão real validada. Não simular conexão.

## Estado desta etapa

A navegação React foi corrigida para manter as seis áreas independentes, na ordem e com os módulos acima. A integração funcional ainda não foi migrada nem validada. A comparação visual final depende das imagens originais `8870.jpg`, `8871.jpg`, `8872.jpg`, `8873.jpg` e `8878.jpg`, ausentes do pacote de códigos.
