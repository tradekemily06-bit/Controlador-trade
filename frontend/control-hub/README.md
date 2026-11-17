# Control Hub React — reconstrução isolada

Esta pasta é uma nova frente de interface. Não substitui nem altera o painel Streamlit, o runtime Python, os módulos existentes ou o EA MQL5.

## Fonte visual e funcional usada

- `streamlit_panel/app.py` do ZIP recebido: nomes e ordem das áreas, módulos, comportamento de navegação, tokens CSS e geometria.
- `streamlit_panel/controlador_trader_referencia_visual.json`: quatro referências visuais e especificação dos estados fechado/aberto.
- As cinco imagens originais `8870.jpg`, `8871.jpg`, `8872.jpg`, `8873.jpg` e `8878.jpg` não vieram dentro do ZIP; a comparação pixel a pixel ainda depende desses arquivos.

## Ordem correta das áreas, conforme app.py

1. CABINE DE COMANDO — Operação; Motor de Decisão; Gestão de Risco; Notificações; Ambiente MT5 DEMO; Kill Switch.
2. ANÁLISE — Análise de Mercado; Memória; Estatísticas; Relatórios.
3. ESTUDO — Laboratório; Replay; Simulador; Aprendizado; Descobertas; Escola / Tutorial / Onboarding.
4. RESERVA FISCAL — Reserva Fiscal.
5. ASSISTENTE DO ECOSSISTEMA — Assistente do Ecossistema.
6. CENTRAL — Financeiro; Configurações; Auditoria; Segurança; Conexões; Multi-Broker.

A referência visual chama as quatro abas principais de COCKPIT, ANÁLISE, ESTUDO e MAIS / ADMIN. O código funcional fornecido já as nomeia CABINE DE COMANDO, ANÁLISE, ESTUDO e CENTRAL e mantém Reserva Fiscal e Assistente do Ecossistema como áreas independentes. A reconstrução segue os nomes e a ordem do código funcional.

## Regras de preservação

- Estado recolhido: botão C circular de 64 × 64 px, fixado a 16 px da esquerda e 16 px da base; manter apenas o conteúdo previsto para esse estado.
- Estado expandido: painel fixado à esquerda e à base, largura `min(34vw, 420px)`, largura máxima `calc(100vw - 32px)`, altura máxima `min(84vh, 460px)`.
- Cores extraídas do código: fundo `#080B0F`, painel `#10151B`, módulos `#161C24`, borda `#25303B`, texto `#E9EEF3`, texto secundário `#7F8B97`, destaque `#46D6AD`.
- REAL permanece desabilitado.
- O estado operacional começa como indisponível; a interface não inventa conexão ou sinal.
- Não conectar ordens nem credenciais nesta etapa.

## Desenvolvimento

```bash
npm install
npm run dev
```

## Estado desta etapa

Apenas a casca React e a navegação visual estão implementadas. As rotas dos módulos e a integração com o runtime ainda não foram migradas. Antes da migração funcional, será produzido um mapa de equivalência para preservar todos os módulos, dados, proteções e comportamentos existentes.
