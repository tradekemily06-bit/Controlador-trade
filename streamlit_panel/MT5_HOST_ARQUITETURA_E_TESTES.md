# Arquitetura candidata — host do Streamlit original no MT5

Status: especificação técnica experimental; não é código de host nem instalador aprovado.

## Restrições invioláveis
- A interface deve ser carregada da aplicação Streamlit original em `http://127.0.0.1:8501`.
- Não editar, reescrever, clonar visualmente, injetar CSS de layout ou substituir `streamlit_panel/app.py`.
- Não usar imagem, HTML estático, React ou mockup como substituto da aplicação.
- Não alterar EA/MQL5, runtime/API, banco, regras fiscais, Assistente, autenticação ou isolamento de titular.
- DEMO/SIMULAÇÃO apenas; nenhuma ordem; REAL bloqueado.
- Não instalar, compilar, publicar ou fazer merge sem autorização específica.

## Decisão técnica provisória
Priorizar uma prova de conceito com Microsoft Edge WebView2 em modo Composition Controller + DirectComposition, em vez de assumir que uma janela pywebview transparente funciona no Windows.

Motivo: a documentação Microsoft descreve composição visual e encaminhamento explícito de eventos de entrada pelo host. O pywebview documenta limitações de transparência e de entrada no backend EdgeChromium do Windows. CEF off-screen permanece alternativa de comparação, mas a disponibilidade de pacote/release, assinatura, checksum, licença e compatibilidade do binário precisam ser verificadas antes de qualquer distribuição.

Esta decisão é apenas uma hipótese de engenharia. Não comprova transparência, encaixe no gráfico, desempenho ou compatibilidade com MT5.

## Desenho de componentes
1. **Streamlit original**: processo existente, supervisor e porta 8501; nenhuma alteração no app.
2. **Runtime existente**: serviço separado na porta 8000; sem mudanças nesta experiência.
3. **Host nativo Windows**: processo independente que cria a superfície de composição e hospeda o WebView2 Composition Controller.
4. **Ancoragem ao MT5**: localizar a janela/área de gráfico alvo, acompanhar posição, tamanho, DPI, minimização, troca de gráfico e fechamento; não assumir dimensões fixas.
5. **Entrada**: converter coordenadas de tela/cliente para coordenadas do WebView2 e encaminhar mouse, roda, teclado e foco. Fora do retângulo interativo do painel, o gráfico e os controles MT5 devem continuar recebendo entrada.
6. **Transparência**: usar composição alfa real; não simular transparência com cor sólida nem aplicar recorte fixo.
7. **Ciclo de vida**: verificar health em `/_stcore/health`; iniciar/recuperar somente serviços locais autorizados; encerrar o host sem encerrar o terminal MT5; registrar logs e permitir reversão.
8. **Segurança**: localhost apenas; sem endpoint de execução novo; sem envio de ordens; respeitar identidade única e bloqueio REAL existentes.

## Provas de conceito — sequência obrigatória
A. Abrir o WebView2 Composition Controller em janela de teste independente, carregar a URL local e confirmar WebSocket, CSS, formulários, gráficos e navegação Streamlit.
B. Demonstrar composição alfa sobre uma janela de teste, com conteúdo atrás visível.
C. Demonstrar encaminhamento de clique, roda, teclado, foco e captura/liberação do mouse; verificar que área externa recebe clique normalmente.
D. Ancorar a superfície à janela de gráfico MT5 sem alterar EA, medindo movimento, redimensionamento, DPI e minimização/restauração.
E. Testar o C recolhido/expandido e o retângulo real do painel, confirmando que BUY/SELL e demais controles não ficam cobertos ou bloqueados.
F. Testar reconexão quando Streamlit/runtime reiniciam, fechamento do MT5, reinicialização do Windows e prevenção de processos duplicados.
G. Executar testes de regressão funcionais em todos os módulos e validar DEMO/SIMULAÇÃO com REAL bloqueado.
H. Comparar capturas do Streamlit original e do painel no MT5 em mesmo tamanho/DPI; qualquer diferença visual não explicada bloqueia aprovação.

## Critérios de aceite
- Hash SHA-256 de `streamlit_panel/app.py` exatamente igual a `DCB0AF794CD28F4E6AE1B023095DC15FCB39EAA4CF393682E2DD0CB86F2960F7`.
- Nenhuma alteração no app, EA, runtime, banco ou proteções.
- Transparência alfa real e interação integral comprovadas no Windows/MT5 real.
- Sem bloqueio fora do painel; BUY/SELL permanecem acessíveis.
- Sem travamentos, vazamento de processos ou regressão funcional nos testes definidos.
- Logs, diagnóstico, recuperação e reversão documentados.
- Aprovação explícita do usuário antes de instalar, fazer merge ou habilitar qualquer operação fora de DEMO.

## Bloqueios que permanecem
- O ZIP aprovado foi recuperado e seu app.py bate com o hash esperado, mas o arquivo ainda não foi inserido nesta branch.
- Esta branch experimental ainda não contém host executável.
- CI de integridade só será verde se o app.py original exato estiver presente; ausência/falha deve bloquear a instalação.
- Não há teste visual ou funcional real no Windows/MT5 deste ambiente.

## Referências
- Microsoft WebView2 overview/features/APIs: https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/overview-features-apis
- pywebview API: https://pywebview.idepy.com/en/guide/api
- pywebview changelog: https://pywebview.flowrl.com/changelog
- CEF Python PR para CEF 147: https://github.com/cztomczak/cefpython/pull/691
- PyPI cefpython3: https://pypi.org/project/cefpython3/


## Atualização de integração — 17/11/2026

### Estado confirmado no repositório

- O arquivo `streamlit_panel/app.py` já foi restaurado nesta branch a partir do arquivo original aprovado.
- SHA-256 esperado e validado no arquivo-fonte recuperado: `DCB0AF794CD28F4E6AE1B023095DC15FCB39EAA4CF393682E2DD0CB86F2960F7`.
- Blob Git do arquivo restaurado: `b28e4e07130a727b231f3e29be542464e534a996`.
- Commit de restauração: `e48bdf03fe12a161f13f7aace9ccd9f867828c24`.
- O supervisor atual mantém o Streamlit em `127.0.0.1:8501`; o host deverá carregar exatamente essa origem. O runtime continua separado em `127.0.0.1:8000`.
- A restauração alterou somente `streamlit_panel/app.py` em relação ao commit anterior da branch. Não houve alteração no EA, runtime, banco, autenticação ou regras fiscais.
- O status de CI para o novo commit ainda não foi confirmado por uma execução consultável. O status combinado do commit não apresentou verificações; isso não deve ser interpretado como CI aprovado.

### Refinamento da decisão WebView2

A documentação Microsoft confirma que o Composition Controller é a API para composição visual e que o host precisa encaminhar eventos de entrada espacial, incluindo mouse, toque e caneta. Também existe um exemplo oficial Win32/C++ de visual composition, que requer Visual Studio com suporte C++ e SDK Windows compatível.

Importante: a existência de Composition Controller **não comprova por si só** que o conteúdo web ficará realmente transparente sobre o gráfico MT5. A documentação de composição também descreve limitações para conteúdo externo/transparência em determinados modelos de composição. Portanto, transparência alfa sobre o gráfico permanece um teste eliminatório, não uma capacidade presumida.

### Próximo trabalho de engenharia

1. Criar uma prova de conceito Win32/C++ isolada, baseada no exemplo oficial Microsoft WebView2SampleWinComp, sem incorporar código no EA.
2. Carregar somente `http://127.0.0.1:8501`; validar WebSocket, navegação e controles reais do Streamlit.
3. Medir composição alfa sobre uma janela de teste e, separadamente, sobre uma janela de gráfico MT5. Se a transparência real falhar, não mascarar o problema com uma janela opaca.
4. Implementar e medir encaminhamento de mouse, roda, teclado e foco; a área fora do painel deve continuar pertencendo ao gráfico.
5. Só depois da prova de conceito independente, testar ancoragem ao gráfico MT5, posição inferior esquerda, estados C recolhido/expandido, DPI e resize.
6. Fazer regressão funcional dos seis espaços do painel, inclusive Reserva Fiscal, Assistente do Ecossistema e CENTRAL/Financeiro.
7. Manter DEMO/SIMULAÇÃO, REAL bloqueado e nenhuma ordem enviada durante todos os testes.

### Limite de validação atual

Este ambiente permite atualizar e auditar o repositório, mas não executa Visual Studio, WebView2 Runtime, Windows ou MetaTrader 5. Assim, ainda não há executável host compilado, prova de transparência, captura do painel no MT5 ou teste de clique no terminal real. Não declarar instalação concluída nem criar um instalador antes dessas evidências.

Referências oficiais:
- WebView2 APIs e composição: https://learn.microsoft.com/pt-br/microsoft-edge/webview2/concepts/overview-features-apis
- Exemplo oficial Win32 com Visual Composition: https://learn.microsoft.com/en-us/microsoft-edge/webview2/samples/webview2samplewincomp


## Revisão técnica após inspeção do sample oficial — 17/11/2026

O sample WinComp da Microsoft foi lido no commit `06d49d546ba5dc0e2773798ee5b982f68275af4c`. Ele é uma demonstração de WebView2 Composition Controller em uma janela Win32 própria, não um exemplo de overlay transparente no gráfico de outro processo.

Achados concretos:
- `AppWindow.cpp` cria Composition Controller e carrega `WebView2SamplePage.html` local.
- `CompositionHost.cpp` cria vários visuais com brushes de cor alfa 255; isso não comprova transparência do WebView sobre o MT5.
- O código de entrada encaminha mensagens de mouse ao `SendMouseInput`, mas não constitui implementação completa de roda, teclado, foco/captura e pointer input para o nosso caso.
- O projeto usa WebView2 `1.0.1056-prerelease` e WIL `1.0.200902.2`; atualizar e validar dependências é obrigatório antes de reutilização.
- A janela hospedeira é própria; não existe ancoragem ou sincronização com o gráfico MT5.

Portanto, o sample só valida que existe uma rota de composição nativa a investigar. Não prova transparência alfa real, clique integral, nem compatibilidade MT5. A arquitetura continua experimental e o host final ainda não foi implementado.

### Estado atual corrigido

- app.py original está presente na branch, com blob Git `b28e4e07130a727b231f3e29be542464e534a996` e SHA-256 aprovado `DCB0AF794CD28F4E6AE1B023095DC15FCB39EAA4CF393682E2DD0CB86F2960F7`.
- URL local do Streamlit: `http://127.0.0.1:8501`.
- Não há host executável nem build validada; não há captura no MT5 nem teste local de transparência/cliques.
- Status CI consultado para o commit então verificado veio sem checks; não equivale a aprovação.
- EA/MQL5, runtime/API, banco, regras fiscais, Assistente, identidade e proteções não foram alterados. REAL permanece bloqueado; nenhuma ordem foi enviada.

### Próxima etapa técnica obrigatória

Criar um protótipo mínimo independente, usando versão estável atual do SDK WebView2 e sem trazer dependências antigas do sample sem revisão. Primeiro provar alfa real em janela de teste quadriculada; depois validar mouse, roda, teclado e foco; só então tentar ancorar no gráfico MT5. Se qualquer etapa falhar, não instalar nem encobrir o problema com janela opaca. Manter a aplicação Streamlit original como única interface.
