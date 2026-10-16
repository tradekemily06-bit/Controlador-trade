# Política de autorreparo seguro

## Regra principal

O ecossistema só pode autorizar um autorreparo automático quando a ação está explicitamente autorizada, é estritamente local, reversível, determinística, previamente validada e limitada por tentativas. A política decide autorização; ela não executa a correção nem emite alertas por conta própria.

## Lista autorizada atual

- `clear_stale_local_cache`: limpar cache local obsoleto, reconstruível e sem perda de estado.

Iniciar/reiniciar o Controlador ou o terminal MT5 **não está autorizado nesta fase**. Essas ações só podem ser consideradas depois que o supervisor provar liveness/health, estado DEMO, reconciliação com o broker e ausência de ordens/posições ativas; um campo booleano enviado pelo chamador não comprova esses fatos. Até essa integração ser validada, falha de processo/terminal deve gerar alerta e bloqueio, sem autorreparo automático. Uma parada controlada solicitada pelo usuário é tratada separadamente da recuperação automática.

Uma ação nova só pode ser adicionada após revisão da implementação e testes específicos. Um nome de ação nunca é prova suficiente de segurança.

## Deve bloquear e encaminhar para supervisão humana

- Ação não incluída na lista autorizada ou causa do problema desconhecida.
- Estado de execução, ordem, posição, ledger, lifecycle ou reconciliação pendente/desconhecida.
- Configuração de risco, autorização REAL, credenciais, permissões, segurança ou alteração irreversível.
- Conta/caminho do MT5 não confirmado como o terminal configurado e conta DEMO.
- Posições/ordens abertas ou não consultáveis durante uma tentativa de recuperação automática do MT5.
- Reparo com efeito externo, não determinístico, não reversível, fora do limite de tentativas, durante cooldown ou com bloqueio de manutenção ativo.

## Comportamento obrigatório

1. Bloquear a ação quando qualquer requisito for falso, ausente ou inválido.
2. Preservar o estado de execução e as travas de segurança; autorreparo nunca concede permissão para operar.
3. Retornar uma causa concreta do bloqueio; o supervisor integrado deve registrar o alerta e indicar a ação humana necessária.
4. Não repetir tentativas em ciclo apertado; respeitar limite e cooldown.
5. Distinguir liveness do processo de diagnóstico operacional: um diagnóstico lento não deve matar um processo que ainda responde ao endpoint leve de liveness.
6. Não transformar falha de dados em sinal de mercado AGUARDAR: análise indisponível deve ser distinguida de uma decisão válida de aguardar.

A integração da política com os supervisores permanece separada do módulo de decisão, para não confundir autorização de reparo com execução de reparo.
