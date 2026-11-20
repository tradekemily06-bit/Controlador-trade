# Viabilidade do host WebView2 no gráfico MT5 — 17/11/2026

## Resultado da inspeção do exemplo oficial

Foi inspecionado o código-fonte oficial da Microsoft em `MicrosoftEdge/WebView2Samples`, diretório `SampleApps/WebView2SampleWinComp`:

- `AppWindow.cpp`
- `AppWindow.h`
- `CompositionHost.cpp`
- `CompositionHost.h`
- `WebView2SampleWinComp.vcxproj`
- `README.md`

Referência oficial: https://github.com/MicrosoftEdge/WebView2Samples/tree/main/SampleApps/WebView2SampleWinComp

## O que o exemplo realmente faz

1. Cria uma janela Win32 própria (`CreateWindowW`).
2. Cria um WebView2 por `CreateCoreWebView2CompositionController`.
3. Cria um `DesktopWindowTarget` usando o HWND da própria janela do exemplo.
4. Cria uma árvore visual de composição e atribui o WebView a um visual.
5. Atualiza os limites do controlador durante o redimensionamento.
6. Encaminha mensagens de mouse recebidas pela janela hospedeira para `SendMouseInput`.

Isso confirma que a API de composição e o encaminhamento explícito de mouse existem. **Não confirma** que o exemplo consiga anexar um painel transparente e clicável a uma janela de gráfico já pertencente ao MetaTrader 5.

## Diferença crítica para este projeto

O exemplo da Microsoft controla a janela Win32 que ele mesmo criou. No nosso caso, a janela e o ciclo de vida pertencem ao MT5. Seria necessário localizar e acompanhar o HWND correto do gráfico, manter o overlay alinhado ao gráfico durante mudanças de tamanho/DPI/aba, gerenciar foco e teclado, e encaminhar entrada sem interceptar os botões BUY/SELL ou bloquear a interação normal com o gráfico.

O exemplo inspecionado não implementa essa integração com MT5, não demonstra transparência alfa real sobre o gráfico do MT5 e não prova que cliques passem corretamente nesse cenário. Portanto, copiar o exemplo e apenas trocar a URL do WebView não seria uma integração válida.

## Decisão técnica nesta etapa

- WebView2 Composition continua como candidato de pesquisa, não como host aprovado.
- Não reutilizar o host de diagnóstico antigo.
- Não criar janela opaca sobre o gráfico nem mascarar o resultado com uma imagem.
- Não alterar o Streamlit original, o EA/MQL5, runtime, banco, regras fiscais ou proteções.
- Não instalar nem declarar concluído antes dos testes no Windows com MT5 real.

## Critérios eliminatórios da prova de conceito

A prova de conceito deverá ser isolada e não enviar ordens. Só poderá avançar se demonstrar, no MT5 DEMO:

1. O gráfico permanece visível em toda a área externa ao painel (transparência real).
2. O painel Streamlit original é carregado de `http://127.0.0.1:8501`, sem CSS/JS injetado que altere sua interface.
3. O clique no C expande/recolhe e todos os controles do Streamlit respondem.
4. Scroll, foco, teclado, redimensionamento, troca de gráfico, DPI, minimizar/restaurar e fechamento funcionam.
5. BUY/SELL e a interação com o gráfico permanecem acessíveis fora da área efetiva do painel.
6. O MT5 não congela nem fica com janela órfã após fechar o host.

Se transparência e encaminhamento de entrada não forem comprovados simultaneamente, esta abordagem deve ser descartada em vez de contornada com uma janela opaca.

## Estado confirmado

- `streamlit_panel/app.py` permanece byte-a-byte preservado na branch experimental, com blob Git `b28e4e07130a727b231f3e29be542464e534a996`.
- O supervisor do Streamlit usa `127.0.0.1:8501` e `/_stcore/health`.
- A inspeção do código-fonte oficial foi feita; nenhuma compilação foi executada aqui.
- Não há evidência de host compilado, teste visual no MT5, instalação local ou validação de cliques.
- Nenhuma alteração no EA, execução de ordens, merge ou deploy foi realizada.

## Próxima ação técnica

Implementar uma prova de conceito nativa mínima, separada do EA e do app Streamlit, somente depois de definir uma estratégia segura de associação ao HWND do gráfico MT5 e de captura/encaminhamento de mouse/teclado. A prova deve ser compilada e testada no Windows do usuário antes de qualquer instalação.