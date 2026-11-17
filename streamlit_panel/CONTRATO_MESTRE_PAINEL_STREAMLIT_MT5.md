# Contrato mestre — Painel Streamlit no MT5

## Objetivo

Preservar o painel Streamlit aprovado como interface operacional do Ecossistema Controlador Trading e fazê-lo abrir/recolher normalmente pelo botão **C** dentro do MetaTrader 5 (MT5), substituindo a atual camada de exibição baseada em WebView2 por uma alternativa mais estável, após avaliação técnica. Este documento consolida os requisitos conhecidos para orientar revisão, implementação e testes.

**Regra central:** corrigir a integração sem redesenhar o painel, sem substituir a aplicação por uma imagem/preview, sem apagar módulos, sem simplificar funcionalidades e sem alterar regras de negócio ou segurança.

## Fonte de verdade e preservação

- A aplicação ativa é o Streamlit em `streamlit_panel/app.py`. O Figma e o JSON visual são apenas referências; não são o painel operacional.
- O arquivo de referência `streamlit_panel/controlador_trader_referencia_visual.json` e as cinco imagens indicadas nele devem permanecer intactos.
- A versão local aprovada de `app.py` foi identificada pelo SHA-256 `DCB0AF794CD28F4E6AE1B023095DC15FCB39EAA4CF393682E2DD0CB86F2960F7`. Antes de qualquer alteração nesse arquivo, comparar com essa referência e explicar a diferença. A preferência é não alterar `app.py`; concentrar a substituição na camada de incorporação/exibição e em testes de integração.
- Não alterar EA/MQL5, runtime/API, banco, Reserva Fiscal, Assistente, dados, lógica de execução, identidade, isolamento por titular ou proteções para resolver um problema visual/de clique.
- Não fazer merge, deploy, instalação no terminal local, sincronização/compilação do EA ou ativação REAL como parte desta tarefa.
- Qualquer mudança deve ficar em branch/PR isolada, com diff revisável. Nunca sobrescrever a branch principal.

## Navegação principal: exatamente seis áreas

A navegação efetiva do Streamlit deve conter exatamente estas seis áreas, nesta ordem e com esta grafia:

1. **CABINE DE COMANDO**
2. **ANÁLISE**
3. **ESTUDO**
4. **RESERVA FISCAL**
5. **ASSISTENTE DO ECOSSISTEMA**
6. **CENTRAL**

Não criar uma sétima área. **Financeiro** permanece como módulo dentro de **CENTRAL**. Não renomear, remover, fundir ou reordenar áreas.

### Módulos conhecidos

Os quatro grupos do JSON de referência continuam intactos. A aplicação Streamlit acrescenta Reserva Fiscal e Assistente do Ecossistema como áreas próprias, sem editar o JSON original.

**CABINE DE COMANDO** (grupo de referência COCKPIT):
- Operação
- Motor de Decisão
- Gestão de Risco
- Notificações
- Ambiente MT5 DEMO (rótulo funcional usado no Streamlit para o item de referência “MT5 DEMO / Simulação”)
- Kill Switch

**ANÁLISE**:
- Análise de Mercado
- Memória
- Estatísticas
- Relatórios

**ESTUDO**:
- Laboratório
- Replay
- Simulador
- Aprendizado
- Descobertas
- Escola / Tutorial / Onboarding

**RESERVA FISCAL**:
- Área própria com estimativas, histórico, períodos, separação Brasil/exterior, filas, revisões e evidências. Manter moedas de origem, conversão e moeda-base conforme regras existentes. Não apresentar estimativa como imposto apurado.

**ASSISTENTE DO ECOSSISTEMA**:
- Área própria, independente de Financeiro.
- Exigir consentimento explícito antes de enviar pergunta/contexto à OpenAI.
- Preservar isolamento por titular, histórico e sanitização já implementados.
- Não executar ordens nem movimentar dinheiro.

**CENTRAL**:
- Financeiro
- Diário Operacional
- Configurações
- Auditoria
- Segurança
- Conexões
- Multi-Broker
- Manter CENTRAL por último. Financeiro não é área principal.

Não declarar um módulo funcional se sua integração real não estiver implementada e validada. Não substituir telas por redirecionamentos enganosos, dados fictícios ou botões sem ação.

## Aparência e identidade visual

Preservar a identidade visual escura do painel. Tokens documentados no JSON:

| Elemento | Valor |
|---|---|
| Fundo principal/gráfico | `#080B0F` |
| Fundo do painel | `#10151B` |
| Fundo dos módulos/cartões | `#161C24` |
| Bordas | `#25303B` |
| Texto principal | `#E9EEF3` |
| Texto secundário | `#7F8B97` |
| Destaque verde-água | `#46D6AD` |

- Manter fundo escuro, grade discreta, tipografia sans-serif semelhante a Inter, títulos em negrito e texto dos módulos em peso regular.
- Manter cartões escuros, cantos arredondados, bordas finas e chevrons nos itens de módulo, conforme referências.
- DEMO deve ser apresentado como cápsula verde-água, com contorno fino.
- Não introduzir cores, efeitos, textos, marcas d'água ou elementos decorativos novos sem referência/aprovação.
- Estado do sistema só pode mostrar “SISTEMA ONLINE” quando a saúde real confirmar; caso contrário, “INDISPONÍVEL”. Não simular disponibilidade.

## Botão C e estados

### Recolhido

- Painel inicia recolhido.
- C circular, alvo de clique de 48×48 px conforme contrato da branch de restauração, no canto inferior esquerdo: `left:18px; bottom:14px`.
- Fundo `#080B0F`, letra e contorno `#46D6AD`, brilho externo discreto.
- Mostrar somente o C, o sinal atual e as porcentagens/score previstos. Não mostrar módulos, título, mensagens técnicas, nomes de arquivos ou textos de desenvolvimento.
- O sinal e o score devem continuar atualizados; o estado recolhido não pode congelar a interface.

### Expandido

- O clique no mesmo C deve abrir o painel completo; o C continua visível e na mesma posição.
- O segundo clique no C recolhe o painel. Não depender de um botão “Fechar painel” separado.
- Painel compacto no canto inferior esquerdo, acima do C, com rolagem interna quando necessário.
- Referência atual da integração: área de recorte de até 436×476 px; shell até 412 px de largura e 400 px de altura. Tratar esses valores como limites do host, não como autorização para redesenhar ou deformar o conteúdo.
- Não cobrir os botões BUY/SELL nem impedir interação com os controles do MT5.
- Não mover o painel para o centro, topo, direita ou outra região.

### Sinal e score

- Sinal ao lado do C no estado recolhido.
- COMPRAR em verde; VENDER em vermelho; AGUARDAR em cor de espera.
- Score de 1 a 100: 1–69 FRACA; 70–79 MODERADA; 80–100 FORTE.
- Preservar o dado de origem; não inventar sinal, percentual ou score quando indisponível.

## Substituição da camada de exibição no MT5 e diagnóstico do clique

- O painel Streamlit original continua sendo a aplicação e a fonte de verdade da interface. O objetivo não é voltar a depender do site aberto no Chrome: o painel deve ser exibido e operado dentro do MT5.
- A integração atual baseada em WebView2 deve ser substituída; não insistir em corrigir indefinidamente essa camada como solução final.
- Antes de escolher a substituta, comparar alternativas tecnicamente viáveis para incorporar a interface no MT5/Windows, considerando estabilidade, compatibilidade, manutenção, desempenho, interação de mouse/teclado, rolagem, transparência e distribuição. Não presumir que uma alternativa funciona sem protótipo e teste.
- A alternativa escolhida deve continuar renderizando a aplicação Streamlit original e suas funcionalidades reais. Não trocar o painel por imagem, mockup, HTML estático, React refeito ou outra interface que apenas imite sua aparência.
- Não abrir o Chrome como solução operacional permanente nem exigir que o usuário acesse um site externo para usar o painel.
- Registrar claramente se a alternativa exige um processo local, serviço local ou componente adicional. O painel deve continuar funcionando dentro do MT5 e não depender de notebook/servidor externo ligado.
- O endereço/porta de saúde usados pela integração devem corresponder ao processo Streamlit realmente iniciado pelo supervisor. O README da branch descreve 8501; houve execução local reportada em 8503. Não deixar launcher e host com portas divergentes ou assumir uma porta sem verificar o processo ativo.
- Investigar a hierarquia HWND, janela pai/filha, estilos, bounds, região de recorte, hit-test e entrega de eventos de mouse da solução atual, para identificar por que o C não responde no MT5 e evitar reproduzir o mesmo defeito na alternativa.
- Distinguir: clique não chega à janela hospedeira; chega à camada de exibição mas não ao DOM; chega ao DOM mas o Streamlit não reroda. Não considerar “janela visível/enabled” prova de que o clique funciona.
- Instrumentar eventos e logs sem expor dados sensíveis. O teste decisivo é clicar no C dentro do MT5 e observar a mudança real de estado; clicar no C no Chrome não valida a integração no terminal.
- Evitar soluções que façam a janela inteira capturar cliques, bloqueiem o gráfico, cubram BUY/SELL ou tornem o overlay click-through.
- Não reescrever o estado `panel_open` do Streamlit sem evidência de defeito nele. Preservar a lógica aprovada do painel.
- Se nenhuma alternativa conseguir hospedar o Streamlit original com estabilidade, apresentar evidências e opções antes de propor qualquer mudança de tecnologia do próprio painel.
## Segurança e operação

- Permanecer em DEMO/SIMULAÇÃO. REAL continua DESABILITADO.
- `execution_allowed` deve continuar falso até processo independente de validação e autorização.
- Não enviar ordens, não testar execução real, não alterar alavancagem/margem e não contornar Kill Switch.
- Preservar identidade confiável, isolamento por titular, auditoria, consentimento do Assistente e regras da Reserva Fiscal.
- Não colocar chaves, tokens, credenciais ou dados privados no GitHub.

## Critérios obrigatórios de aceite

1. Diff prova que os arquivos originais protegidos não foram alterados sem autorização explícita.
2. As seis áreas aparecem na ordem e grafia exatas.
3. Todos os módulos e funcionalidades existentes continuam acessíveis; nenhum módulo é apagado ou substituído por placeholder.
4. C inicia recolhido, abre com um clique dentro do MT5 e recolhe com outro clique.
5. C permanece no canto inferior esquerdo e na mesma posição nos dois estados.
6. Sinal/score são consistentes e atualizados nos dois estados.
7. Painel não cobre BUY/SELL nem bloqueia interação com o gráfico fora da sua área.
8. Host conecta ao Streamlit ativo e à porta correta, confirmando health.
9. Testes automatizados passam, mas não substituem o teste manual no Windows com MT5 DEMO real.
10. Capturas do Streamlit e do MT5 são comparadas às cinco referências originais antes de declarar fidelidade visual.
11. REAL permanece bloqueado; nenhuma ordem é enviada.
12. Não fazer merge/deploy/instalação sem autorização explícita.

## Prompt mestre para implementação

> Trabalhe no repositório Controlador-trade respeitando integralmente este contrato. Primeiro audite a branch, o diff e os arquivos atuais. Não presuma que um PR anterior está correto só porque existe ou porque a CI passou. Preserve os arquivos originais e suas funções; não reescreva o painel, não recrie o Figma, não substitua Streamlit por React, imagem estática ou preview. Mantenha exatamente as seis áreas, seus nomes, ordem, módulos, cores, dados, lógica e proteções descritos aqui. O problema prioritário é o C não expandir/recolher e a tela branca/preta dentro do MT5, embora o painel funcione no Chrome. Substitua a camada de exibição baseada em WebView2 por uma alternativa tecnicamente validada que hospede o Streamlit original dentro do MT5. Compare alternativas, faça protótipo e testes de compatibilidade, clique, rolagem, estabilidade e desempenho antes de escolher. Investigue também HWND, recorte, hit-test e eventos de mouse da integração atual para não repetir o defeito. Não use o Chrome como solução operacional permanente. Verifique a porta real do Streamlit e alinhe launcher/integração. Não declare correção sem teste real de clique no MT5 DEMO. Não altere EA/MQL5, runtime, dados fiscais, Assistente, identidade ou execução. Não habilite REAL, não envie ordens, não faça instalação local, deploy ou merge. Entregue diff, testes, evidências e limitações; se qualquer requisito não puder ser provado, declare-o pendente em vez de inventar sucesso.
