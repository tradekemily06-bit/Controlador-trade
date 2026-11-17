# Control Hub React — reconstrução isolada

Esta pasta é uma nova frente de interface. Não substitui nem altera o painel Streamlit, o runtime Python, os módulos existentes ou o EA MQL5.

## Fonte visual usada

- `streamlit_panel/app.py` fornecido no pacote de auditoria: tokens CSS e geometria do estado recolhido/expandido.
- `streamlit_panel/controlador_trader_referencia_visual.json`: nomes de áreas, módulos e tokens visuais.
- O pacote recebido não contém as cinco imagens originais `8870.jpg`, `8871.jpg`, `8872.jpg`, `8873.jpg` e `8878.jpg`; a comparação pixel a pixel permanece pendente até essas imagens serem fornecidas.

## Regras de preservação

- Estado recolhido: botão C circular de 64 × 64 px, fixado a 16 px da esquerda e 16 px da base.
- Estado expandido: painel fixado à esquerda e à base, largura `min(34vw, 420px)`, largura máxima `calc(100vw - 32px)`, altura máxima `min(84vh, 460px)`.
- Cores extraídas do código de referência: fundo `#080B0F`, painel `#10151B`, módulos `#161C24`, borda `#25303B`, texto `#E9EEF3`, texto secundário `#7F8B97`, destaque `#46D6AD`.
- REAL permanece desabilitado.
- O estado operacional começa como indisponível; a interface não inventa conexão ou sinal.
- Não conectar ordens nem credenciais nesta etapa.

## Desenvolvimento

```bash
npm install
npm run dev
```

## Estado desta etapa

Apenas a casca visual React e a navegação local estão implementadas. Os módulos ainda não foram ligados ao runtime. Antes dessa migração, será feito o mapa de equivalência funcional para não perder Reserva Fiscal, Assistente do Ecossistema, Financeiro, auditoria, segurança, memória, estatísticas, Replay, Simulador e as demais funções existentes.
