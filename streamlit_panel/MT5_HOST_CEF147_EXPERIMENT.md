# Experimento de integração MT5 — preservação do Streamlit original

## Regra inviolável

Este experimento NÃO altera, copia, reescreve, redesenha ou substitui a aplicação Streamlit. O arquivo `streamlit_panel/app.py` continua sendo a única fonte da interface e dos módulos.

- Base do experimento: `fix/mt5-order-state-reconciliation-20261110`, commit `fef6e3d33658160e8f519175d5c107220783b531`.
- Blob de `streamlit_panel/app.py` na base: `3e27419ffee9d175bc2984ce6348e9be8f2dc957`.
- SHA-256 de referência aprovada registrado no contrato mestre: `DCB0AF794CD28F4E6AE1B023095DC15FCB39EAA4CF393682E2DD0CB86F2960F7`.
- O PR #528 contém alterações em `app.py`; por isso ele não é a base deste experimento. Nenhuma alteração daquele arquivo será trazida para cá.

## Objetivo

Substituir somente a camada hospedeira WebView2 por uma camada Chromium Embedded Framework (CEF) separada, capaz de exibir a aplicação Streamlit original no gráfico MT5. O processo Streamlit e o runtime permanecem os serviços existentes; o host não executa ordens e não altera o EA.

## Candidato técnico

O CEF Python oficial recebeu uma atualização para CEF 147 e suporte declarado a Python 3.10–3.14, incluindo Windows 10+ x64, em PR integrado em 2 de novembro de 2026 na branch `cefpython147`. Porém, a página oficial do PyPI ainda lista somente a versão 66.1, publicada em 2021. Portanto, a atualização moderna ainda não é uma dependência de instalação simples e estável via PyPI. Isso torna CEF uma opção de protótipo, não uma escolha aprovada para distribuição. Antes de fixar dependência, será necessário verificar release oficial, origem, assinatura/checksum, compatibilidade Python 3.12 x64 e licença. Nada disso prova compatibilidade com este painel ou com o MT5.

A implementação experimental deverá priorizar renderização off-screen com transparência alfa real e encaminhamento explícito de mouse/teclado. Não deverá simplesmente colocar uma janela opaca sobre o gráfico. O recorte, a posição inferior esquerda, o C e os botões BUY/SELL precisam ser preservados. Não usar HTML estático, React, imagem, mockup ou reconstrução da interface.

## Verificações obrigatórias antes de qualquer instalação

1. A verificação SHA-256 deve confirmar que `app.py` é exatamente a versão aprovada. Se falhar, interromper: não substituir a referência por outra versão.
2. Validar o Streamlit original no host CEF com a mesma URL local e a porta efetivamente usada pelo supervisor.
3. Confirmar que CSS, JavaScript, WebSocket, navegação, formulários, gráficos, Reserva Fiscal e Assistente continuam operacionais.
4. Confirmar transparência real: o gráfico MT5 deve permanecer visível fora dos elementos do painel.
5. Confirmar que clique no C chega ao Streamlit, expande e recolhe sem travar.
6. Confirmar scroll, foco, teclado, redimensionamento, DPI, minimização/restauração e fechamento do MT5.
7. Confirmar que o overlay não bloqueia o gráfico nem os botões BUY/SELL fora de sua área.
8. Executar apenas em MT5 DEMO/SIMULAÇÃO; REAL permanece bloqueado e nenhuma ordem pode ser enviada.
9. Produzir capturas comparativas do Streamlit original e do painel dentro do MT5. Só declarar fidelidade após comparação visual.
10. Não fazer merge, instalação local, deploy ou alteração do EA sem autorização específica.

## Limitação conhecida

O GitHub permite preservar e distribuir os arquivos, mas não fornece acesso ao Windows/MT5 do usuário. Testes automatizados de CI não substituem a validação final no terminal real. Até essa validação, o host será experimental e não deve ser tratado como instalador pronto.
