# Pacote-fonte do painel aprovado — MT5

Este diretório é uma cópia de referência isolada para preparar a integração do painel ao MT5. Não substitui o painel ativo, não altera o EA, runtime/API, banco de dados ou proteções DEMO/REAL.

## Fontes preservadas

- `source/streamlit_panel/app.py`: aplicação Streamlit completa copiada da branch `experiment/mt5-streamlit-cef147-host-20261117`.
- `source/streamlit_panel/presentation.py`: apresentação dos sinais.
- `source/streamlit_panel/trusted_identity.py`: validação/extração de identidade confiável.
- `source/streamlit_panel/controlador_trader_referencia_visual.json`: especificação visual derivada das referências Figma.
- `source/streamlit_panel/requirements.txt`: dependências específicas do painel.

## Estrutura funcional

O app contém seis destinos principais: Cabine de Comando, Análise, Estudo, Reserva Fiscal, Assistente do Ecossistema e Central. Financeiro permanece dentro de Central.

## Fidelidade visual

A especificação registra os tokens escuros e verde-água, estados C recolhido/expandido e os quatro grupos visuais originais. O JSON é uma especificação extraída das capturas; não é o JSON interno original do arquivo Figma.

## Limite técnico importante

O Streamlit é uma aplicação web conectada ao runtime. Este pacote ainda não é um frontend React/HTML autônomo nem prova de renderização dentro do gráfico MT5. A camada nativa no gráfico continua sendo o EA MQL5; a integração WebView2 precisa ser validada separadamente.

## Próximas etapas

1. Comparar visualmente as cinco capturas originais com a renderização do painel.
2. Extrair a camada de apresentação para um frontend independente, mantendo contratos e regras de negócio existentes.
3. Conectar o frontend ao runtime existente sem duplicar lógica, dados ou operações.
4. Validar no MT5 DEMO; REAL permanece bloqueado.

Nenhum arquivo original foi substituído. Nenhuma ordem foi enviada.
