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


## Nota complementar: transparência do WebView2 (documentação atual)

A API `ICoreWebView2Controller2::DefaultBackgroundColor` aceita fundo totalmente transparente (alfa 0) ou totalmente opaco (alfa 255); valores semitransparentes não são aceitos. Fundo transparente significa que o WebView não pinta seu fundo padrão. Isso **não torna transparentes os elementos da página**: se o HTML/CSS do Streamlit pintar um fundo opaco em toda a área, esse conteúdo continuará cobrindo o que está atrás. Além disso, a documentação do Windows Visual Layer alerta que conteúdo externo como WebView2 tem limitações de composição/transparência e não pode ser tratado como um visual comum.

Consequência para o painel: ainda é necessário provar, com a página original sem alteração, se o layout real deixa áreas externas transparentes. Não se deve injetar CSS ou reescrever o Streamlit para forçar transparência, pois isso violaria o requisito de preservar o app original. O teste de aceitação precisa mostrar o gráfico através das áreas vazias do painel, além de confirmar cliques, roda, teclado, foco, DPI, redimensionamento e comportamento ao trocar/minimizar gráficos.

Referências oficiais consultadas em 17/11/2026:
- WebView2 `DefaultBackgroundColor`: https://learn.microsoft.com/en-us/microsoft-edge/webview2/reference/win32/icorewebview2controller2?view=webview2-1.0.3912.50
- Visão geral das APIs WebView2 e composição: https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/overview-features-apis
- Limitações da Visual Layer com conteúdo externo: https://learn.microsoft.com/en-us/windows/apps/develop/composition/visual-layer


## Correção de estado e pendências reais — 17/11/2026

Esta seção prevalece sobre afirmações históricas anteriores neste documento que estejam em conflito com ela.

### Estado verificado
- `streamlit_panel/app.py` está restaurado na branch e seu blob Git é `b28e4e07130a727b231f3e29be542464e534a996`; o SHA-256 aprovado é `DCB0AF794CD28F4E6AE1B023095DC15FCB39EAA4CF393682E2DD0CB86F2960F7`.
- A aplicação original não foi editada para esta integração.
- O Streamlit é servido em `http://127.0.0.1:8501`; runtime separado em `http://127.0.0.1:8000`.
- A branch permanece experimental. Ainda não existe host nativo implementado/compilado, nem instalador, nem validação visual/funcional no MT5.
- A ausência de status/checks consultáveis não significa CI aprovado.

### Trabalho ainda necessário — sem atalhos
1. Implementar um host Windows nativo isolado com WebView2 Composition Controller, sem alterar `app.py`, EA ou runtime.
2. Compilar em Windows com SDK e WebView2 Runtime suportados; fixar versões e registrar artefatos/checksums.
3. Provar transparência alfa com a página original e fundo quadriculado. Fundo transparente do controller, isoladamente, não prova transparência do HTML/CSS do Streamlit.
4. Implementar e testar encaminhamento de clique, roda, teclado, foco/captura e cursor; garantir que eventos fora do painel continuem no gráfico.
5. Testar ancoragem à janela de gráfico MT5, DPI, resize, minimização/restauração, troca de gráfico e encerramento.
6. Validar os seis espaços originais e todos os controles, incluindo o C recolhido/expandido, sem bloquear BUY/SELL.
7. Executar somente em DEMO/SIMULAÇÃO, confirmar REAL bloqueado e ausência de envio de ordens.
8. Só depois gerar pacote reversível e solicitar autorização específica para instalação. Não fazer merge/deploy automaticamente.

**Critério de honestidade:** até haver build Windows, logs, capturas e testes reproduzíveis no MT5 real, não afirmar que a integração está concluída ou instalada. Este repositório/ambiente não tem acesso à sessão Windows/MT5 do usuário.

## Prova de compilação WebView2 — preparação automatizada — 17/11/2026

Foi adicionada ao workflow de CI uma etapa Windows isolada que:
- verifica o hash original, a sintaxe Python e tenta iniciar o Streamlit em 127.0.0.1:8501, consultando /_stcore/health;
- baixa o exemplo oficial Microsoft WebView2 Composition em commit fixo 06d49d546ba5dc0e2773798ee5b982f68275af4c;
- altera somente a navegação do exemplo temporário, durante o job, para apontar para o Streamlit local; não altera o código do exemplo no repositório nem o app.py;
- tenta compilar o protótipo isolado x64 e publica o executável como artefato de CI se a compilação for bem-sucedida.

**Limite desta prova:** o exemplo oficial ainda abre sua própria janela Win32. Isso testa compilação e carregamento do Streamlit dentro de um WebView2 Composition Controller, mas não implementa a janela transparente sobre o gráfico MT5, a ancoragem ao gráfico nem o encaminhamento completo de entrada. O artefato, se gerado, é somente protótipo de bancada e não instalador do Controlador Trading.

O job foi adicionado ao workflow; até consultar resultado success e inspecionar o artefato, não declarar compilação aprovada. Mesmo com build verde, a integração MT5 ainda depende dos testes alfa/input e ancoragem em Windows com o MetaTrader real.


## Resultado CI Windows após correção de hash — 17/11/2026

Execução: https://github.com/tradekemilly06-bit/Controlador-trade/actions/runs/44185706018
Commit testado: `3f729da4b12ad5a2f392ef90a964ceac9da3d6e2`.

Os três jobs terminaram com sucesso:
- `verify-original-app`: hash byte a byte no runner Linux aprovado.
- `windows-streamlit-smoke`: hash normalizado para CRLF/LF aprovado, dependências instaladas, `py_compile` aprovado e Streamlit iniciou em `127.0.0.1:8501`; endpoint `/_stcore/health` respondeu `ok`.
- `webview2-composition-build`: dependências restauradas e exemplo Win32/C++ oficial WebView2 Composition compilado em x64 Release.

Artefato gerado: `webview2-composition-streamlit-poc`, 55.515 bytes, SHA-256 `0a24fbe13e22eb4c71575277e69ec50add2608589531b708cebc2b74e8f504b0`. É o executável de prova de conceito do exemplo Microsoft apontado ao Streamlit local durante o job. Não é o host MT5 final nem instalador.

### O que este resultado comprova
- O arquivo original está íntegro e não foi modificado.
- O app Streamlit inicia em runner Windows e responde ao health check local.
- O sample WebView2 Composition compila em runner Windows x64.

### O que NÃO comprova
- Que a janela é transparente sobre outra janela/processo.
- Que o painel está ancorado ao gráfico MT5.
- Que mouse, roda, teclado, foco e eventos fora do painel funcionam corretamente no MT5.
- Que o executável pode ser instalado ou usado como painel final.

Próxima etapa obrigatória: executar a prova visual e de entrada em Windows interativo, primeiro em janela de teste com fundo quadriculado, depois em MT5 DEMO. Sem acesso a uma sessão Windows/MT5 interativa neste ambiente, esses critérios continuam pendentes e não devem ser simulados por CI headless.


## Atualização de dependências para a próxima prova Windows — 17/11/2026

A auditoria do projeto oficial mostrou que o sample fixado usa WebView2 `1.0.1056-prerelease` e WIL `1.0.200902.2`, versões antigas que não devem ser tratadas como base de distribuição.

Foi atualizado o workflow experimental para, somente no checkout temporário do sample Microsoft durante o CI, testar:
- Microsoft WebView2 SDK estável `1.0.4314.35`;
- Microsoft Windows Implementation Library estável `1.0.260126.7`.

O código original do sample permanece fixado no commit Microsoft `06d49d546ba5dc0e2773798ee5b982f68275af4c`; a troca de versões é feita no runner, não altera o repositório do fornecedor nem o `app.py` aprovado. O objetivo é verificar se o exemplo de composição ainda compila com dependências atuais antes de escrever o host próprio.

**Estado desta alteração:** workflow atualizado no commit `0e5cf376efa763d34a2f52a9f0767548be4a24e4`. A execução CI correspondente ainda precisa ser consultada; não declarar o build com SDK atualizado como aprovado até o resultado aparecer.

**Limite mantido:** mesmo que a compilação passe, ainda será apenas o sample de janela própria. Isso não entrega ancoragem ao MT5, transparência real da página Streamlit, nem encaminhamento completo de eventos. O host específico do Controlador Trading continua por implementar e validar em Windows interativo.


## Correção técnica após falha do SDK estável — 17/11/2026

O CI com WebView2 Release SDK `1.0.4314.35` compilou o restante do sample, mas falhou em `CompositionHost.h` porque o include `WebView2Experimental.h` não existe no pacote Release. O erro não é uma falha do Streamlit nem do WIL.

A documentação oficial da Microsoft confirma que pacotes Release contêm somente APIs estáveis, enquanto APIs experimentais exigem SDK Prerelease e runtime de preview. Por isso, o teste experimental foi corrigido para usar WebView2 `1.0.4365-prerelease` com WIL `1.0.260126.7`. A alteração está isolada no workflow, sem modificar o app original ou qualquer componente operacional.

**Implicação importante:** um build bem-sucedido com SDK Prerelease ainda não prova que a API funciona no WebView2 Runtime estável instalado no computador do usuário. A documentação Microsoft recomenda canal Edge Preview para APIs experimentais. Portanto, esse caminho é apenas investigação de protótipo; não será usado como dependência de produção sem promoção da API para Release ou uma alternativa baseada somente em APIs estáveis.

Referência oficial: https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/versioning


## Revisão da hipótese sobre o cabeçalho experimental — 17/11/2026

A inspeção do código-fonte confirmou que o sample inclui `WebView2.h` no cabeçalho pré-compilado e usa os tipos `ICoreWebView2CompositionController` e `ICoreWebView2Environment3`, que a referência Win32 da Microsoft documenta como APIs estáveis desde WebView2 1.0.774.44. O include extra `WebView2Experimental.h` é legado do sample fixado, não prova por si só que a composição exija runtime Preview.

Para evitar depender de API experimental sem necessidade, o workflow foi ajustado novamente: usa Release SDK `1.0.4314.35`, WIL `1.0.260126.7` e remove somente, no checkout temporário do sample, o include legado `WebView2Experimental.h`. A compilação agora vai confirmar se as declarações estáveis de `WebView2.h` bastam. Não foi feita alteração no código oficial do sample no repositório Microsoft nem no app aprovado.

Esta revisão substitui a tentativa intermediária com SDK Prerelease como caminho de teste. O resultado de compilação do novo workflow ainda é necessário; se falhar por símbolos realmente ausentes, será reavaliada a versão/API com base no erro exato.

Referências: https://learn.microsoft.com/en-us/microsoft-edge/webview2/reference/win32/icorewebview2compositioncontroller e https://learn.microsoft.com/en-us/microsoft-edge/webview2/reference/win32/icorewebview2environment3


## Resultado da compilação estável WebView2 — 17/11/2026

Execução CI: https://github.com/tradekemilly06-bit/Controlador-trade/actions/runs/44187162958
Commit testado: `de4be4dcb88839c1469cee2df454b34a44772eb4`.

Os três jobs terminaram com sucesso:
- `verify-original-app`: hash do `app.py` aprovado.
- `windows-streamlit-smoke`: dependências instaladas, compilação Python aprovada e health check do Streamlit respondeu `ok` em `127.0.0.1:8501`.
- `webview2-composition-build`: o exemplo oficial WebView2 Composition compilou em Windows x64 Release usando WebView2 SDK estável `1.0.4314.35` e WIL `1.0.260126.7`.

Artefato de bancada: `webview2-composition-streamlit-poc`, 58.164 bytes; SHA-256 `782b057ea9cf1b183cae4306dea0258dcfc73d5a69eea7641af8a44067112ef4`. O executável é o exemplo Microsoft em uma janela Win32 própria, apontado para o Streamlit local durante o job. Não é o host Controlador Trading, não está ancorado ao MT5 e não deve ser instalado como painel.

### Limites que continuam bloqueando a integração

Este resultado confirma compilação do exemplo e inicialização do Streamlit em runner Windows. Não confirma transparência alfa sobre o gráfico, encaminhamento completo de mouse/roda/teclado/foco, ancoragem ao gráfico, comportamento do C recolhido/expandido ou preservação dos cliques BUY/SELL.

O próximo teste válido exige Windows interativo com WebView2 Runtime e MetaTrader 5: primeiro janela quadriculada para provar alfa e eventos; depois gráfico MT5 em DEMO/SIMULAÇÃO. Até esses testes existirem, não criar instalador, não instalar, não alterar EA/MQL5, runtime, banco, regras fiscais, Assistente, autenticação ou o `app.py` original. REAL continua bloqueado e nenhuma ordem foi enviada.


## Resultado confirmado da execução CI 44187162958 — 17/11/2026

Execução: https://github.com/tradekemilly06-bit/Controlador-trade/actions/runs/44187162958

Commit testado: `de4be4dcb88839c1469cee2df454b34a44772eb4`.

Resultado: **success** nos três jobs:
- `verify-original-app`: hash do arquivo original aprovado confirmado.
- `windows-streamlit-smoke`: dependências instaladas, compilação Python aprovada e Streamlit iniciou em `127.0.0.1:8501`; o endpoint `/_stcore/health` respondeu `ok`.
- `webview2-composition-build`: o exemplo oficial Microsoft Win32/WebView2 Composition, fixado no commit `06d49d546ba5dc0e2773798ee5b982f68275af4c`, compilou em Release x64 com WebView2 SDK estável `1.0.4314.35` e WIL `1.0.260126.7`.

Artefato gerado: `webview2-composition-streamlit-poc`, ID `14374937169`, SHA-256 `782b057ea9cf1b183cae4306dea0258dcfc73d5a69eea7641af8a44067112ef4`. Disponível até 15/02/2027. Link da execução acima, seção Artifacts.

**Escopo exato desta aprovação:** o artefato é o exemplo Microsoft adaptado apenas dentro do runner temporário do CI para navegar até o Streamlit local. Ele cria uma janela Win32 própria. Não é o host final, não está ancorado no gráfico MT5 e não prova transparência alfa real, foco, roda, teclado, captura de mouse ou ausência de bloqueio dos botões BUY/SELL.

O workflow e os arquivos de documentação foram os únicos itens alterados nesta etapa de CI; `streamlit_panel/app.py` não foi modificado. Não houve alteração do EA/MQL5, runtime/API, banco, regras fiscais, Assistente, identidade ou proteções. Nenhuma instalação, merge, deploy ou ordem foi realizada.

**Próxima etapa:** construir um host Win32 independente e específico para o painel, sem copiar a interface e sem alterar o Streamlit; primeiro demonstrar transparência e entrada em janela de teste, depois estudar ancoragem ao gráfico MT5. Os testes visuais e de interação precisam ocorrer em Windows com MT5 real e não podem ser substituídos por CI headless.


## Análise do DOM original e estratégia de recorte — 17/11/2026

Inspeção somente de leitura do início de `streamlit_panel/app.py` confirmou:
- O fundo global `.stApp` é explicitamente opaco (`#080B0F`) e tem grade CSS.
- O botão C recolhido e a área expandida são elementos fixos separados: `.st-key-panel-toggle` e `.st-key-control-hub-shell`, ambos ancorados a 16 px da esquerda e de baixo.
- A área expandida tem largura máxima de 420 px e altura máxima de 460 px; o botão C tem 64×64 px.
- Logo, deixar o WebView transparente não resolve o fundo opaco da página. Não é permitido alterar CSS nem injetar estilos no painel para forçar transparência.

### Nova hipótese técnica a testar (sem mudar o app)
Em vez de exigir transparência alfa da página inteira, investigar um **recorte visual do WebView2 Composition**:
1. Manter o viewport do navegador no tamanho integral da área do gráfico, para que os elementos `position: fixed` continuem ancorados ao canto inferior esquerdo correto.
2. Consultar, por leitura do DOM, os retângulos reais de `.st-key-panel-toggle` e `.st-key-control-hub-shell`.
3. Aplicar um clip à visual tree do WebView2 para mostrar somente a união desses retângulos. O fundo global opaco ficaria fora da região renderizada, sem editar o CSS ou o arquivo original.
4. Encaminhar entrada apenas dentro da região visível; fora dela, os cliques continuam pertencendo ao MT5.
5. Recalcular o clip após rerun Streamlit, expansão/recolhimento, scroll, mudança de DPI e resize.

Esta hipótese pode contornar a necessidade de transparência CSS da página, mas **ainda não está comprovada**. É necessário verificar se o Composition Controller permite manter viewport integral e clip dinâmico sem distorcer layout, se o hit testing acompanha o clip e se os eventos do Streamlit continuam íntegros. Se não funcionar, parar e documentar; não aplicar CSS, não alterar `app.py` e não instalar janela opaca.

### Segurança de escopo
A inspeção foi somente de leitura. Nenhum arquivo da aplicação, EA/MQL5, runtime/API, banco, regras fiscais, identidade ou proteções foi alterado. O app continua sendo a única interface. A branch é experimental e não foi instalada no MT5.


## Protótipo de recorte visual no CI — 17/11/2026

Foi atualizado o workflow para aplicar, **somente no checkout temporário do exemplo Microsoft dentro do runner Windows**, uma prova de conceito de recorte:
- manter o WebView2 com o viewport integral da janela de teste;
- reduzir a árvore visual a um único visual WebView;
- aplicar `InsetClip` de 420×460 px no canto inferior esquerdo;
- restringir o encaminhamento de mouse à mesma região visível;
- continuar navegando para o Streamlit original em `127.0.0.1:8501`.

O patch não é aplicado ao repositório Microsoft, não é código de produção e não altera o `app.py`. O objetivo imediato é apenas verificar se a API de recorte compila junto com a Composition Controller estável. A execução CI deste novo commit ainda precisa ser consultada.

**Limitações deliberadas deste teste:** o retângulo é fixo, não é medido dinamicamente do DOM; o sample ainda abre janela própria; não acompanha o gráfico MT5; não prova alpha/hit testing fora da janela; não implementa roda, teclado, foco, captura, DPI ou ciclo de vida. Portanto, mesmo que compile, é somente uma etapa de engenharia, não uma integração utilizável.

Próximo passo após a compilação: substituir o retângulo fixo por medidas DOM dos elementos `.st-key-panel-toggle` e `.st-key-control-hub-shell`, receber atualizações após reruns e validar coordenadas e input. Nenhuma alteração visual/CSS no app original é permitida.


## Resultado do protótipo de recorte fixo — 17/11/2026

Execução CI: https://github.com/tradekemily06-bit/Controlador-trade/actions/runs/44195935805
Commit: `87b9c0bc69d09eb8e9091b6e49b85bcd14059f72`.

Os três jobs terminaram com sucesso:
- `verify-original-app`: hash SHA-256 aprovado do `streamlit_panel/app.py`.
- `windows-streamlit-smoke`: dependências instaladas, módulos Python compilados e Streamlit respondeu `ok` em `127.0.0.1:8501`.
- `webview2-composition-build`: sample Microsoft Win32/WebView2 Composition compilou em Windows x64 Release com SDK estável WebView2 `1.0.4314.35` e WIL `1.0.260126.7`, agora com clip fixo 420×460 no canto inferior esquerdo e hit-test de mouse limitado à mesma região.

Artefato de bancada: `webview2-streamlit-clipped-viewport-poc`, ID `14378388959`, SHA-256 do ZIP `9e5d80d91cfbbf5c5c3910d8b16b05f7ca67dd3cb3e1d7d53920e56045cdb5d0`. É somente o sample oficial modificado temporariamente no runner CI; não é host final nem instalador.

### O que este resultado prova — e o que não prova

Prova que a alteração de recorte fixo compila com a Composition Controller estável e que o Streamlit original inicia no runner Windows. Não prova que o retângulo realmente fica transparente sobre o MT5, que o C não congela, nem que os eventos de mouse, roda, teclado, foco, captura, resize e DPI funcionam em uso real. O teste de hit-test é apenas a implementação básica de mouse do protótipo e precisa ser ampliado.

### Próxima implementação isolada

1. Separar o botão C recolhido em uma camada de controle nativa independente do viewport/fundo do Streamlit.
2. Fazer o C nativo e o estado de expansão da página Streamlit compartilharem um único estado abrir/fechar por mensagem explícita; evitar que o C dependa de uma superfície opaca ou de um retângulo cobrindo o gráfico.
3. Substituir o clip fixo por retângulos DOM lidos dos elementos originais `.st-key-panel-toggle` e `.st-key-control-hub-shell`, com atualização após reruns e mudanças de estado.
4. Implementar ciclo completo de entrada e vida da janela: mouse, roda, teclado, foco, captura, cursor, resize e DPI. Fora das regiões clicáveis, o MT5 deve continuar recebendo os eventos.
5. Testar primeiro em janela quadriculada interativa; só então testar ancoragem e interação no gráfico MT5 em DEMO/SIMULAÇÃO.

A separação do C é uma arquitetura a implementar, não uma função já entregue. Não alterar `app.py`, CSS, EA/MQL5, runtime/API, banco, regras fiscais, Assistente, autenticação ou proteções. Nenhuma instalação local, merge, deploy ou ordem foi realizada.


## Ponte DOM somente leitura para controle nativo C — 17/11/2026

Foi criado `streamlit_panel/mt5_host/dom_bridge.js` no commit `450c3bb7a097aae96b7475d8bac299a9f71a4aa2`. O arquivo é um script que o futuro host WebView2 deverá registrar com `AddScriptToExecuteOnDocumentCreated`.

### Comportamento implementado no script

- Observa os seletores já existentes no `app.py`: `.st-key-panel-toggle` e `.st-key-control-hub-shell`.
- Mede o botão C real quando recolhido e a caixa real do painel quando expandido, usando `getBoundingClientRect()`.
- Informa ao host estado, retângulos, tamanho do viewport e `devicePixelRatio` via `window.chrome.webview.postMessage`.
- Usa MutationObserver, resize e scroll para atualizar medidas após reruns e mudanças de layout.
- Recebe `{type:"controlador.toggle"}` do host e aciona o botão C do Streamlit correspondente ao estado atual.
- Não injeta CSS, não oculta elementos, não modifica o DOM nem altera `app.py`.

### Limites e próximos passos

O script é apenas a ponte de observação/comando. Ele não cria a janela nativa C, não desenha o botão, não aplica clip, não faz composição alfa e não corrige sozinho congelamentos. O host C++ ainda precisa:
1. Criar e manter um controle C nativo independente da superfície WebView2.
2. Registrar a ponte antes de carregar `http://127.0.0.1:8501` e receber mensagens `WebMessageReceived`.
3. Converter coordenadas CSS para pixels físicos usando DPR e coordenadas do cliente da janela.
4. Aplicar clip dinâmico à visual do WebView2 para mostrar apenas a caixa expandida; no estado recolhido, mostrar somente o C nativo e não a área de fundo do Streamlit.
5. Enviar `controlador.toggle` ao receber clique no C nativo, com proteção contra cliques repetidos enquanto o Streamlit processa o rerun.
6. Implementar mouse, roda, teclado, foco, captura e cursor apenas dentro da área expandida; fora dela, o gráfico MT5 recebe os eventos.
7. Testar em janela quadriculada interativa e, depois, em MT5 DEMO.

Foi adicionado ao CI o passo `node --check streamlit_panel/mt5_host/dom_bridge.js`. Esse passo valida sintaxe JavaScript, não comportamento DOM nem integração WebView2. A aprovação do CI não deve ser interpretada como prova de ausência de congelamento ou transparência real.

O arquivo `app.py` permanece sem alterações e deve continuar correspondendo ao SHA-256 aprovado `DCB0AF794CD28F4E6AE1B023095DC15FCB39EAA4CF393682E2DD0CB86F2960F7`. Nenhuma instalação, merge, deploy, alteração EA/MQL5, runtime, banco, identidade ou regra operacional foi feita.


## Escopo fechado de conclusão e evidências — 17/11/2026

Esta lista consolida os critérios já definidos acima. Ela não autoriza alterar a interface original nem ampliar o produto. O trabalho de integração só será considerado concluído quando todos os portões abaixo tiverem evidência reproduzível:

1. **Integridade:** SHA-256 de `streamlit_panel/app.py` igual ao aprovado; teste automatizado de contrato do C recolhido/expandido e dos seletores originais.
2. **Inicialização:** Streamlit original inicia no Windows, health check responde e o host não cria processos duplicados; recuperação e encerramento não fecham o MT5.
3. **Host próprio:** executável Win32 x64 do Controlador Trading, código-fonte versionado, SDK/runtime WebView2 identificados e build reproduzível. O sample Microsoft sozinho não satisfaz este item.
4. **Composição/recorte:** página original carregada sem alteração; viewport integral; C nativo independente; clip dinâmico baseado nos retângulos DOM reais; fora das regiões do painel o gráfico permanece visível.
5. **Entrada:** clique, roda, teclado, foco, captura/liberação e cursor testados; hit testing respeita o recorte e os eventos fora do painel chegam ao MT5.
6. **Ancoragem:** painel acompanha gráfico/janela, posição, resize, DPI, minimização/restauração, troca de gráfico e encerramento.
7. **Regressão visual e funcional:** comparação com o Streamlit original; navegação e controles de todos os módulos/áreas existentes continuam funcionais; C recolhido mostra apenas o controle/sinal previsto; expandido não cobre BUY/SELL.
8. **Estabilidade e segurança:** teste de sessão prolongada, reruns/reconexão, reinício dos serviços e ausência de congelamento/processos órfãos; DEMO/SIMULAÇÃO apenas, REAL bloqueado e nenhuma ordem enviada.
9. **Entrega reversível:** logs, instruções de inicialização/recuperação, pacote e procedimento de reversão; só depois pedir autorização específica para instalar no MT5.

### O que não será apresentado como conclusão
- CI verde de hash, sintaxe, health check ou compilação do sample não substitui os testes visuais/interativos.
- O protótipo de clip fixo não substitui o clip DOM dinâmico.
- A ponte JavaScript não substitui o host C++.
- Não serão criados requisitos de redesign, migração do app, alteração do EA/runtime/banco ou liberação de REAL como condição para esta integração.

### Critério de transparência sobre imprevistos
Se um dos testes revelar defeito técnico necessário para cumprir qualquer portão acima, ele será registrado como correção dentro desse mesmo portão, com causa e evidência. Se surgir dependência realmente fora do escopo (por exemplo, limitação incompatível do WebView2/Windows/MT5), ela será comunicada antes de qualquer mudança de arquitetura ou pedido de alteração. Não será escondida nem declarada como concluída por aproximação.

**Estado no momento desta atualização:** o teste de contrato do painel foi adicionado ao CI. Na execução `44197528022`, a verificação de hash, sintaxe e ponte DOM terminou com sucesso; os jobs de instalação/health do Streamlit e compilação do sample WebView2 ainda estavam em andamento quando consultados. O host nativo próprio e os testes interativos no Windows/MT5 continuam pendentes.


## Matriz de entrada WebView2 — requisitos de implementação confirmados na API — 17/11/2026

A leitura da referência Win32 atual da Microsoft detalha que a integração não pode encaminhar apenas `WM_LBUTTONDOWN`:

- **Mouse:** mapear cada evento Win32 para `COREWEBVIEW2_MOUSE_EVENT_KIND`, converter coordenadas para o espaço cliente do WebView e enviar os modificadores/botões em `virtualKeys`.
- **Roda vertical/horizontal:** encaminhar `WM_MOUSEWHEEL` e `WM_MOUSEHWHEEL` como `COREWEBVIEW2_MOUSE_EVENT_KIND_WHEEL` / `HORIZONTAL_WHEEL`; `mouseData` precisa preservar o delta assinado, em unidades de `WHEEL_DELTA=120`.
- **Captura:** se um arrasto começar dentro do painel e o ponteiro sair da janela hospedeira, usar `SetCapture` / `ReleaseCapture` e continuar enviando os eventos até liberar o botão; cancelar captura corretamente se a janela perder foco ou for destruída.
- **Saída do ponteiro:** enviar `COREWEBVIEW2_MOUSE_EVENT_KIND_LEAVE` quando o ponteiro sair da região WebView para encerrar hover/popups corretamente.
- **Cursor:** registrar `CursorChanged`, consultar `get_Cursor` e aplicar o cursor no HWND hospedeiro via `WM_SETCURSOR`; manter cópia válida do handle quando necessário.
- **Toque/caneta:** se forem suportados pelo terminal e pelo host, converter mensagens de ponteiro do Windows em `COREWEBVIEW2_POINTER_INFO` e chamar `SendPointerInput`. Caso não sejam implementados, registrar explicitamente como não suportados, sem afirmar entrada integral.
- **Foco/teclado:** o Composition Controller também implementa `ICoreWebView2Controller`; usar as APIs herdadas de foco/visibilidade e tratar `GotFocus`, `LostFocus`, `MoveFocusRequested` e `AcceleratorKeyPressed`. Não presumir que encaminhar apenas mouse faz teclado funcionar.
- **Área fora do painel:** o hit-test do host deve usar exatamente a mesma geometria física usada pelo clip. Evento fora da região não deve ser consumido pelo host; deve seguir para a janela/gráfico MT5.

Esses requisitos são extraídos da API, não significam que já estejam implementados. A matriz passa a fazer parte do critério de aceite de entrada e estabilidade.

Referências Microsoft:
- Win32 C++ Composition Controller: https://learn.microsoft.com/en-us/microsoft-edge/webview2/reference/win32/icorewebview2compositioncontroller
- CoreWebView2CompositionController e detalhes de mouse/pointer/cursor: https://learn.microsoft.com/en-us/microsoft-edge/webview2/reference/winrt/microsoft-web-webview2-core/corewebview2compositioncontroller
- Visão geral de APIs e composição: https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/overview-features-apis


## Correção de inconsistências históricas e desenho de implementação do host — 17/11/2026

Esta seção prevalece sobre qualquer trecho anterior desta página que diga que o app.py aprovado não foi recuperado/inserido. O arquivo está restaurado na branch experimental; o hash esperado é `DCB0AF794CD28F4E6AE1B023095DC15FCB39EAA4CF393682E2DD0CB86F2960F7`, e os jobs recentes de integridade/contrato passaram. A aplicação original permanece intocada.

### Estado real, sem confundir protótipo com entrega
- Existe uma ponte JavaScript somente de leitura que mede o C e o shell e comunica o estado ao host.
- Existem testes automatizados da ponte DOM e do contrato estrutural do app original.
- O CI inicia o Streamlit em Windows e compila um checkout temporário do exemplo Microsoft WebView2 Composition.
- **Ainda não existe código C++ próprio do host do Controlador Trading.** O EXE produzido pelo CI é um sample temporário da Microsoft, não o painel integrado.
- Não existe teste interativo de transparência, entrada ou ancoragem no MT5 real.

### Decisão de composição que deve orientar o host

Não tentar tornar transparente o fundo da página Streamlit. O app original pinta seu próprio fundo, e o arquivo não pode ser alterado. Em vez disso, o host deve limitar a superfície visual do WebView ao retângulo medido do shell original enquanto expandido. Assim, o WebView pode continuar com seu fundo original dentro do retângulo e não desenha fora dele; o gráfico permanece visível fora da área recortada.

O C recolhido deve ser uma janela/visual Win32 nativo independente. No estado recolhido, ocultar o visual WebView e manter somente o C nativo. No estado expandido, mostrar o visual WebView recortado ao retângulo real recebido pela ponte e manter o C nativo como controle de fechar/recolher. Não depender do fundo opaco da página para desenhar ou detectar o C.

A geometria de recorte e hit-test deve ter uma única fonte: `expandedShell` publicado pela ponte. O host deve validar a mensagem (tipo, versão, dimensões finitas, retângulo dentro do viewport e tamanho máximo razoável), converter CSS pixels para o espaço físico esperado pelo controller usando DPI/escala da janela correta e aplicar exatamente o mesmo retângulo ao clip e ao hit-test. Mensagem ausente, inválida, obsoleta ou viewport incompatível deve falhar fechado: ocultar WebView, manter C nativo disponível e não capturar eventos do gráfico.

### Máquina de estados mínima

| Estado | C nativo | Visual WebView | Entrada |
|---|---|---|---|
| Iniciando / sem health | visível e clicável | oculto | apenas C |
| Recolhido | visível | oculto | clique no C inicia/solicita abertura do Streamlit |
| Expandido | visível | visível, recortado ao shell | somente dentro do shell |
| Rerun / layout inválido | visível | oculto até nova medição válida | nenhum evento capturado pelo WebView |
| MT5 minimizado/fechado | oculto ou encerrado de forma limpa | oculto | sem processos órfãos |

A ponte não pode alternar estado por conta própria com base em mensagens duplicadas. O host mantém um identificador/geração de layout, rejeita retângulos antigos e só considera expandido depois de receber uma medição válida após o clique e o rerun do Streamlit.

### Ordem de implementação do código nativo

1. **Host de bancada Win32 próprio:** janela de teste com padrão quadriculado, C nativo, inicialização/encerramento WebView2, URL local configurável com padrão `http://127.0.0.1:8501`, log e health check. Nenhuma ligação ao MT5 nesta etapa.
2. **Ponte e recorte dinâmico:** registrar `dom_bridge.js` com `AddScriptToExecuteOnDocumentCreated`, validar `WebMessageReceived`, atualizar clip e visibilidade com o estado e o retângulo reais. Medir DPI e conversão de coordenadas.
3. **Entrada completa:** mouse (incluindo movimento, botões, duplo clique, X buttons, roda vertical/horizontal e leave), captura/liberação, cursor, foco/teclas e PointerInput. Eventos fora do retângulo não são consumidos.
4. **Teste interativo de bancada:** comprovar com capturas que o padrão quadriculado aparece fora do retângulo e que controles reais Streamlit funcionam sem congelar.
5. **Ancoragem MT5:** somente depois da bancada aprovada, criar adaptador para localizar e acompanhar a janela/área do gráfico MT5, incluindo troca de gráfico, resize, DPI, minimize/restore e encerramento. Não modificar EA.
6. **Regressão e pacote reversível:** testar módulos e ciclo de vida; produzir logs, versão, checksums e rollback. Instalação só com autorização explícita.

### Condições de bloqueio
- Não chamar o sample Microsoft de host próprio.
- Não afirmar transparência real apenas porque `DefaultBackgroundColor` é alfa zero: a estratégia é recorte visual do conteúdo opaco ao retângulo DOM, e isso também precisa ser comprovado visualmente.
- Não instalar, fazer merge, alterar EA ou habilitar REAL.
- Se a prova de bancada demonstrar que Composition Controller não permite o recorte/input necessários, parar e comparar outra tecnologia antes de reescrever arquitetura.

Referências primárias:
- https://learn.microsoft.com/en-us/microsoft-edge/webview2/reference/win32/icorewebview2compositioncontroller
- https://learn.microsoft.com/en-us/microsoft-edge/webview2/reference/win32/icorewebview2controller2
- https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/overview-features-apis


## Resultado confirmado da prova Windows de composição recortada — 17/11/2026

Execução CI: https://github.com/tradekemily06-bit/Controlador-trade/actions/runs/44197855019

Os três jobs concluíram com sucesso:
- `verify-original-app`: sintaxe e testes da ponte DOM, contrato do painel e hash do app aprovado.
- `windows-streamlit-smoke`: dependências, compilação Python e health check do Streamlit em Windows.
- `webview2-composition-build`: o sample Microsoft Win32/WebView2, temporariamente apontado para `127.0.0.1:8501` e com experimento de viewport recortado, compilou x64 Release.

Artefato: `webview2-streamlit-clipped-viewport-poc`, ID `14379472889`, 55.492 bytes, SHA-256 do ZIP `6110dc6275bf7c8c8b915e3e0f18f8d97141e034ed8899487f62d5445552cb8f`.

**Interpretação correta:** é uma prova de compilação do sample temporário Microsoft, não do host próprio Controlador Trading. A compilação não prova que o retângulo recortado corresponde ao shell dinâmico em runtime, que o padrão de fundo fica visível fora dele, que a entrada completa funciona ou que a janela se ancora ao MT5. Nenhum executável foi instalado no computador do usuário.

A execução seguinte `44197911247` já aprovou integridade/contrato e o smoke test Windows; no último acompanhamento, o job de build WebView2 ainda estava em execução. A branch continua experimental.


### Segunda execução integral de CI — 17/11/2026

Execução: https://github.com/tradekemily06-bit/Controlador-trade/actions/runs/44197911247 — **3/3 jobs concluídos com sucesso**: integridade/contrato, Streamlit Windows e compilação do sample WebView2 Composition.

Artefato repetido: `webview2-streamlit-clipped-viewport-poc`, ID `14380226452`, 55.496 bytes, SHA-256 do ZIP `4bcd2bc17b307d905087404aa12824007752f650fabad16879eb7add6898b23f`.

Isso confirma reprodutibilidade da compilação do sample em uma segunda execução, não transforma o sample em host final nem substitui a prova interativa visual/de entrada no MT5.

## Auditoria do CSS original e consequência para o recorte — 17/11/2026

Leitura somente, sem modificar o arquivo streamlit_panel/app.py (hash aprovado preservado):

- .stApp define fundo opaco #080B0F e grade de fundo.
- .st-key-panel-toggle define o C com fundo próprio.
- .st-key-control-hub-shell define o painel com posição fixa inferior esquerda, left: 16px, bottom: 16px, largura máxima de 420px e altura máxima de 460px.

**Consequência importante:** configurar DefaultBackgroundColor do WebView2 como alfa zero não torna o documento transparente: o CSS original pinta o fundo opaco de toda a aplicação. Portanto, não se deve exibir o WebView inteiro sobre o gráfico esperando que o MT5 apareça através do fundo da página.

A arquitetura correta continua sendo recortar a composição ao retângulo real medido de .st-key-control-hub-shell quando expandido e ocultar o WebView quando recolhido. O C recolhido deve ser desenhado pelo host nativo e não pode depender do fundo do WebView. O retângulo de recorte precisa vir da mensagem de layout do DOM bridge; 420×460 é somente limite de bancada e não pode ser tratado como geometria final.

A medição deve validar viewport, DPR e retângulo finito/positivo, converter CSS px para coordenadas físicas e rejeitar mensagens antigas ou incompatíveis. Se a medição falhar, ocultar a composição e manter apenas o C nativo; nunca ampliar o recorte para a janela inteira.

### Estado da auditoria de entrada

- A execução CI 44199256895 compilou com sucesso o mapeamento explícito de mensagens Win32 para COREWEBVIEW2_MOUSE_EVENT_KIND.
- A execução CI 44199479008 compilou com sucesso a conversão das coordenadas de tela da roda para coordenadas client da janela.
- Esses testes compilam a alteração temporária aplicada ao sample Microsoft; não validam ainda o encaminhamento no MT5, captura durante arraste, teclado/foco, nem geometria dinâmica baseada no DOM bridge.

Referência oficial da API de composição: https://learn.microsoft.com/en-us/microsoft-edge/webview2/reference/win32/icorewebview2compositioncontroller


## Evidência CI mais recente e limite do artefato — 17/11/2026

Execução: https://github.com/tradekemily06-bit/Controlador-trade/actions/runs/44199728637
Commit: `3969521d01bde25c1aa9da057a7c12e316d1d56e`.

Os três jobs concluíram com sucesso:
- `verify-original-app`: SHA-256 do `streamlit_panel/app.py` confere exatamente com o original aprovado.
- `windows-streamlit-smoke`: dependências instaladas, compilação Python aprovada e Streamlit respondeu `ok` em `http://127.0.0.1:8501/_stcore/health`.
- `webview2-composition-build`: compilação x64 Release do sample Win32/C++ da Microsoft concluída.

Artefato gerado: `webview2-streamlit-clipped-viewport-poc`, 55.724 bytes, SHA-256 `fd316ec6515c5dd730fa40ee11bde63e130dc8cc503b503d64dae1effb2cf58c`. Ele continua sendo o sample Microsoft modificado apenas durante o job: a navegação aponta para Streamlit local e o clip/hit-test são fixos em 420x460 para bancada. Não é o host Controlador Trading, não usa ainda o retângulo dinâmico enviado pelo DOM e não comprova transparência real, entrada completa ou integração com MT5.

### Próximo gate de implementação

Não promover esse artefato nem chamá-lo de host. O próximo incremento deve ser um projeto Win32/C++ próprio, com fonte versionado no repositório e build x64 reproduzível no CI, que substitua o sample como unidade de compilação. O projeto deve começar com janela de bancada independente e separar explicitamente: criação do Composition Controller, visual/clip, controle C nativo, protocolo de mensagens DOM e roteamento de entrada. A geometria fixa 420x460 do sample é somente teste temporário; a integração final precisa consumir `expandedShell` e `viewport.dpr` reais, rejeitar mensagens inválidas/obsoletas e manter o WebView oculto quando recolhido.

O host próprio ainda não foi implementado nesta atualização. A próxima implementação não deve alterar `app.py`, EA/MQL5, runtime, banco, identidade, Reserva Fiscal, Assistente ou bloqueio REAL.


## Roteador nativo de entrada compilado no Windows CI — 17/11/2026

Execução: https://github.com/tradekemily06-bit/Controlador-trade/actions/runs/44202688816
Commit do workflow: `1aab00ada6e696ac066b70aec8766968ede5e223`.

Os três jobs terminaram com sucesso. No job Windows de composição, foram concluídos:
- compilação e execução dos contratos de geometria/DPI/hit-test;
- compilação e execução do contrato de entrada WebView2;
- compilação e execução de `native_input_router.test.cpp`, incluindo o header `native_input_router.h`;
- compilação x64 Release do sample oficial WebView2 Composition temporariamente apontado ao Streamlit local;
- publicação do artefato de prova de conceito.

O teste do roteador verifica a tradução das mensagens e as decisões de roteamento/captura contra o contrato. A compilação confirma compatibilidade do helper com MSVC e o SDK WebView2 fixado. **Não** comprova captura real no desktop, funcionamento de cursor em uma janela viva, teclado/foco, composição visual ou ancoragem ao MT5: o roteador ainda não está conectado a um host próprio.

O arquivo `streamlit_panel/app.py` continuou protegido pelo teste de hash aprovado. Nenhuma alteração foi feita no EA/MQL5, runtime/API, banco, Reserva Fiscal, Assistente, identidade ou bloqueio REAL. Nenhuma instalação, merge ou envio de ordem foi realizado.

### Gate seguinte

Implementar e compilar um executável Win32 próprio, inicialmente como janela de bancada independente. Somente depois de validar ciclo de vida, Composition Controller, C nativo, clip DOM dinâmico e entrada completa em bancada será razoável iniciar a etapa de ancoragem ao gráfico MT5. A prova atual não autoriza afirmar que o painel já aparece no MT5.
