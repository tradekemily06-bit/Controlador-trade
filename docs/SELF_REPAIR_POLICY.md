# Política de autorreparo seguro

## Regra principal

O ecossistema só pode autorizar um autorreparo automático quando a ação está explicitamente autorizada, é estritamente local, reversível, determinística, previamente validada e limitada por tentativas. A política decide autorização; ela não executa a correção nem emite alertas por conta própria.

## Lista autorizada atual

- `clear_stale_local_cache`: autorização limitada para limpar cache local obsoleto, desde que todos os requisitos de segurança sejam comprovados na solicitação.

Essa é uma lista intencionalmente restrita. Um nome de ação não comprova que ela é segura. Nenhuma outra ação pode ser autorizada até que seja adicionada explicitamente à lista após revisão da implementação e testes específicos. A autorização, por si só, não prova que a execução concreta está segura.

## Deve bloquear e encaminhar para supervisão humana

- Ação não incluída na lista autorizada ou causa do problema desconhecida.
- Estado de execução, ordem, posição, ledger, lifecycle ou reconciliação pendente/desconhecida.
- Configuração de risco, autorização REAL, credenciais, permissões, segurança ou alteração irreversível.
- Problema em corretora/terminal externo, conectividade, dados ausentes/ambíguos ou qualquer situação sem causa conhecida e reparo validado.
- Reparo com efeito externo, não determinístico, não reversível, fora do limite de tentativas, durante cooldown ou com bloqueio de manutenção ativo.

## Comportamento obrigatório

1. Bloquear a ação quando qualquer requisito for falso, ausente ou inválido.
2. Preservar o estado de execução e as travas de segurança; autorreparo nunca concede permissão para operar.
3. Retornar uma causa concreta do bloqueio; o supervisor integrado deve registrar o alerta e indicar a ação humana necessária.
4. Não repetir tentativas em ciclo apertado; respeitar limite e cooldown.
5. Não transformar falha de dados em sinal de mercado AGUARDAR: análise indisponível deve ser distinguida de uma decisão válida de aguardar.

A integração da política com os supervisores deve permanecer separada do módulo de decisão, para não confundir autorização de reparo com execução de reparo.
