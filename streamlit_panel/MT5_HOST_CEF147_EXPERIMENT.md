# Experimento de integração MT5 — preservação do Streamlit original

## Regra inviolável

Este experimento NÃO altera, copia, reescreve, redesenha ou substitui a aplicação Streamlit. O arquivo `streamlit_panel/app.py` continua sendo a única fonte da interface e dos módulos.

- Base do experimento: `fix/mt5-order-state-reconciliation-20261110`, commit `fef6e3d33658160e8f519175d5c107220783b531`.
- Blob de `streamlit_panel/app.py` na base: `3e27419ffee9d175bc2984ce6348e9be8f2dc957`.
- SHA-256 de referência aprovada registrado no relatório local de 16/11: `DCB0AF794CD28F4E6AE1B023095DC15FCB39EAA4CF393682E2DD0CB86F2960F7`.
- Conferência independente do `app.py` da base Git: `C6011F3AB3B3EBD8ACA4CDE7F328BB802635F1EBA86A24B96AA6919C57F6109B` — NÃO corresponde à referência aprovada.
- O `app.py` recuperado da Biblioteca também não corresponde: `2E4FD51CD371FF17A35E7D413944112C31E696BC4D9FA2119EEB976C265C4A13`.
- O PR #528 contém alterações em `app.py`; por isso ele não é a base deste experimento. Nenhuma alteração daquele arquivo será trazida para cá.
- **BLOQUEIO ATUAL:** o arquivo binário exato que gerou o hash aprovado `DCB0...` ainda não foi recuperado do GitHub nem da Biblioteca. Esta branch é somente uma preparação isolada e NÃO deve ser instalada. É necessário recuperar o `app.py` original exato ou seu ZIP e confirmar o SHA-256 antes de qualquer integração.

## Objetivo

Substituir somente a camada hospedeira WebView2 por uma camada Chromium Embedded Framework (CEF) separada, capaz de exibir a aplicação Streamlit original no gráfico MT5. O processo Streamlit e o runtime permanecem os serviços existentes; o host não executa ordens e não altera o EA.

## Candidato técnico

O CEF Python oficial recebeu uma atualização para CEF 147 e suporte declarado a Python 3.10–3.14, incluindo Windows 10+ x64, em PR integrado em 2 de novembro de 2026 na branch `cefpython147`. Porém, a página oficial do PyPI ainda lista somente a versão 66.1, publicada em 2021. Portanto, a atualização moderna ainda não é uma dependência de instalação simples e estável via PyPI. Isso torna CEF uma opção de protótipo, não uma escolha aprovada para distribuição. Antes de fixar dependência, será necessário verificar release oficial, origem, assinatura/checksum, compatibilidade Python 3.12 x64 e licença. Nada disso prova compatibilidade com este painel ou com o MT5.

A implementação experimental deverá priorizar renderização off-screen com transparência alfa real e encaminhamento explícito de mouse/teclado. Não deverá simplesmente colocar uma janela opaca sobre o gráfico. O recorte, a posição inferior esquerda, o C e os botões BUY/SELL precisam ser preservados. Não usar HTML estático, React, imagem, mockup ou reconstrução da interface.

## Verificações obrigatórias antes de qualquer instalação

1. **Bloqueio atual:** recuperar o arquivo `app.py` que produziu o SHA-256 aprovado `DCB0...`; as duas cópias examinadas não correspondem. Não instalar nem adaptar o painel até obter correspondência exata.
2. A verificação SHA-256 deve confirmar que `app.py` é exatamente a versão aprovada. Se falhar, interromper: não substituir a referência por outra versão.
3. Validar o Streamlit original no host CEF com a mesma URL local e a porta efetivamente usada pelo supervisor.
4. Confirmar que CSS, JavaScript, WebSocket, navegação, formulários, gráficos, Reserva Fiscal e Assistente continuam operacionais.
5. Confirmar transparência real: o gráfico MT5 deve permanecer visível fora dos elementos do painel.
6. Confirmar que clique no C chega ao Streamlit, expande e recolhe sem travar.
7. Confirmar scroll, foco, teclado, redimensionamento, DPI, minimização/restauração e fechamento do MT5.
8. Confirmar que o overlay não bloqueia o gráfico nem os botões BUY/SELL fora de sua área.
9. Executar apenas em MT5 DEMO/SIMULAÇÃO; REAL permanece bloqueado e nenhuma ordem pode ser enviada.
10. Produzir capturas comparativas do Streamlit original e do painel dentro do MT5. Só declarar fidelidade após comparação visual.
11. Não fazer merge, instalação local, deploy ou alteração do EA sem autorização específica.

## Limitação conhecida

O GitHub permite preservar e distribuir os arquivos, mas não fornece acesso ao Windows/MT5 do usuário. Testes automatizados de CI não substituem a validação final no terminal real. Até essa validação, o host será experimental e não deve ser tratado como instalador pronto.


## Recuperação do ZIP original — 17/11/2026

O ZIP localizado na Biblioteca é `Controlador-trade_PAINEL_CABINE_CENTRAL_ORDEM_CORRIGIDA.zip` (1.878.997 bytes). Foi materializado e inspecionado localmente, sem alterar seu conteúdo.

- Caminho de trabalho da cópia recuperada: `/mnt/data/mt5_original_zip/Controlador-trade_PAINEL_CABINE_CENTRAL_ORDEM_CORRIGIDA.zip`.
- Entrada exata: `streamlit_panel/app.py`.
- Tamanho: 197.038 bytes.
- SHA-256 calculado diretamente dos bytes extraídos: `DCB0AF794CD28F4E6AE1B023095DC15FCB39EAA4CF393682E2DD0CB86F2960F7`.
- **RESULTADO: correspondência exata com o hash aprovado.** O bloqueio de recuperação do app.py foi resolvido. O arquivo do ZIP é agora a referência aprovada para a integração. Não substituir por app.py de outro branch ou PR.

### O que o ZIP contém e o que falta

O ZIP contém a aplicação Streamlit original, dependências, runtime, EA e o supervisor Streamlit. A configuração oficial do supervisor inicia o painel em `127.0.0.1:8501` (health em `/_stcore/health`). O README também documenta a porta 8501.

O ZIP **não contém** `mt5_webview_host.py` nem outro host de navegador embutido no gráfico MT5. Portanto, o arquivo da aplicação está recuperado, mas a integração gráfica continua pendente.

### Host antigo encontrado na Biblioteca — não reutilizar diretamente

Foi recuperado `mt5_webview_host_DIAGNOSTICO.py` (8.880 bytes; SHA-256 `09BD4668E1E329DA45AF9EDCC61B187770E1AF027799C4A36E74C2684ABCB02F`). É uma versão de diagnóstico WebView2 que:

- fixa URL em `http://127.0.0.1:8503`, enquanto o supervisor deste ZIP usa a porta 8501;
- exige um hash antigo `A3AA...`, diferente do app.py agora aprovado;
- injeta CSS que altera a posição vertical do painel (`bottom: 46px`) e aplica recorte fixo de 436×476, sem validação para o viewport atual;
- depende de pywebview/EdgeChromium e inclui monitor de eventos para investigar perda de clique.

Esse host não deve ser executado nem ter seu hash simplesmente trocado. O diagnóstico antigo é uma pista para investigar o problema de clique, não uma integração pronta.

### Próxima etapa técnica

Preparar uma camada hospedeira separada que aponte para `127.0.0.1:8501`, sem injetar CSS que altere o layout original, sem editar `streamlit_panel/app.py`, sem substituir a interface e sem tocar no EA/runtime. A camada deve validar dinamicamente a saúde do Streamlit e a janela correta do MT5, encaminhar mouse/teclado, respeitar o retângulo real do painel e preservar o gráfico e os controles BUY/SELL. A escolha CEF/WebView2 permanece experimental até comprovar transparência, eventos de clique, DPI, redimensionamento e estabilidade no Windows/MT5 real.

Nenhuma instalação local, compilação do EA, ordem, merge ou deploy foi realizada nesta etapa.
