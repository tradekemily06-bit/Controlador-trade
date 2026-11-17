# Control Hub React — reconstrução isolada

Esta pasta é uma nova frente de interface. Não substitui nem altera o painel Streamlit, o runtime Python, os módulos existentes ou o EA MQL5.

## Organização funcional confirmada no app.py

A navegação possui exatamente quatro áreas principais, nesta ordem:

1. **CABINE DE COMANDO**
   - Operação
   - Motor de Decisão
   - Gestão de Risco
   - Notificações
   - Ambiente MT5 DEMO
   - Kill Switch
   - Assistente do Ecossistema

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

4. **CENTRAL**
   - Financeiro
   - Configurações
   - Auditoria
   - Segurança
   - Conexões
   - Multi-Broker
   - Reserva Fiscal

A nomenclatura e a ordem foram conferidas no bloco `AREAS` do `app.py`. A interface não cria abas principais separadas para Reserva Fiscal ou Assistente do Ecossistema.

## Referência visual e dimensões

- C fechado: botão circular de 64 × 64 px, 16 px da esquerda e 16 px da base; leitura do sinal/score/estado ao lado.
- C permanece no mesmo ponto e acima da janela do painel também no estado aberto, conforme a regra de sobreposição do host e a posição aprovada pelo usuário.
- Painel: posição fixa à esquerda e à base, `left: 16px`, `bottom: 16px`, `width: min(34vw, 560px)`, `max-width: calc(100vw - 32px)`, `max-height: calc(100vh - 32px)`.
- Cores: fundo `#080B0F`, painel `#10151B`, módulos `#161C24`, borda `#25303B`, texto `#E9EEF3`, texto secundário `#7F8B97`, destaque `#46D6AD`.
- Cabeçalho: `Controlador-Trader` e selo `DEMO`.
- Linhas dos módulos: cartões horizontais escuros, texto à esquerda e chevron à direita.
- Rodapé: Estado do sistema, Alavancagem e REAL — DESABILITADO.
- O sinal e o score ainda são apresentados como indisponíveis nesta casca visual. Não se simula uma conexão real.

## Mapa de integração funcional

| Área/módulo | Implementação existente a preservar |
|---|---|
| Operação | `/api/health` |
| Motor de Decisão | última análise de mercado da sessão |
| Gestão de Risco | `/api/risk` |
| Notificações | `/api/notifications` |
| Ambiente MT5 DEMO | `/api/connections` |
| Kill Switch | estado de proteção em `/api/health` |
| Assistente do Ecossistema | `show_assistant()`, histórico e consentimento por envio |
| Análise de Mercado | `show_market_analysis()` |
| Memória | `/api/memory?limit=50` |
| Estatísticas | `/api/statistics` |
| Relatórios | `/api/statistics` |
| Laboratório / Aprendizado / Descobertas | `/api/learning` |
| Replay | `show_replay()` |
| Simulador | `show_simulator()` |
| Escola / Tutorial / Onboarding | `/api/onboarding` |
| Financeiro | `show_finance_overview()` |
| Configurações | `/api/preferences`, com proteções de execução mantidas |
| Auditoria | `/api/security/audit` |
| Segurança | `/api/health` e trilha de auditoria |
| Conexões / Multi-Broker | `/api/connections` |
| Reserva Fiscal | `show_fiscal()` e endpoints `/api/fiscal-reserve/*` |

Este mapa é um inventário de destinos existentes, não uma alegação de que eles já foram migrados para React. A migração deverá preservar validações, isolamento por proprietário, consentimento do Assistente, trilhas de auditoria, classificação fiscal pendente e bloqueio de execução REAL.

## Desenvolvimento

```bash
npm install
npm run dev
```

## Estado desta etapa

A casca React, a navegação de quatro áreas e os estilos principais foram montados em branch isolada. A integração funcional ainda não foi migrada nem validada. A comparação pixel a pixel permanece pendente das cinco imagens originais `8870.jpg`, `8871.jpg`, `8872.jpg`, `8873.jpg` e `8878.jpg`, que não estavam no pacote de códigos.
