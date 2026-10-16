# Política de autorreparo seguro

## Regra principal

O ecossistema só pode autorizar um autorreparo automático quando a ação é conhecida, estritamente local, reversível, determinística, previamente validada e limitada por tentativas. A política decide autorização; ela não executa a correção.

## Pode ser autorizado (após avaliação)

- Correção local e reversível de um estado derivado/cache que possa ser reconstruído sem perda.
- Reparo cujo resultado possa ser verificado por teste/checagem determinística antes de retomar o serviço.
- No máximo o limite explícito de tentativas, com período de espera controlada e sem bloqueio de manutenção ativo.

## Deve bloquear e alertar para supervisão humana

- Estado de execução, ordem, posição, ledger, lifecycle ou reconciliação pendente/desconhecida.
- Configuração de risco, autorização REAL, credenciais, permissões, segurança ou alteração irreversível.
- Problema em corretora/terminal externo, conectividade, dados ausentes/ambíguos ou qualquer situação sem causa conhecida e reparo validado.
- Reparo com efeito externo, não determinístico, não reversível, fora do limite de tentativas, durante cooldown ou com bloqueio de manutenção ativo.

## Comportamento obrigatório

1. Bloquear a ação quando qualquer requisito for falso, ausente ou inválido.
2. Preservar o estado de execução e as travas de segurança; autorreparo nunca concede permissão para operar.
3. Gerar alerta com causa concreta e ação humana necessária quando a política bloquear.
4. Não repetir tentativas em ciclo apertado; respeitar limite e cooldown.
5. Não transformar falha de dados em sinal de mercado AGUARDAR: análise indisponível deve ser distinguida de uma decisão válida de aguardar.

A integração da política com os supervisores deve permanecer separada do módulo de decisão, para não confundir autorização de reparo com execução de reparo.
