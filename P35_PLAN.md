# P35 — Deduplicação e controle seguro de entrega de alertas

## Objetivo
Evitar que o mesmo incidente operacional seja entregue repetidamente enquanto preserva a fronteira de entrega criada no P34.

## Regras
- reutilizar `OperationalAlert`/`OperationalAlertReport` do P33 e `AlertDeliveryMessage`/`AlertSink` do P34;
- deduplicação é determinística e baseada no conteúdo do alerta;
- somente alertas idênticos ao último alerta com a mesma chave são suprimidos;
- a memória de deduplicação é explicitamente volátil e não é tratada como persistência operacional;
- nenhum alerta pode alterar kill switch, execução, recuperação ou mercado;
- nenhum retry automático, replay ou chamada externa é introduzido;
- entrada inválida falha de forma explícita;
- a ordem dos alertas recebidos é preservada;
- um novo alerta diferente volta a ser entregue normalmente.

## Critério de encerramento
Existe uma camada testada entre P33 e P34 que controla duplicatas consecutivas de forma determinística, sem esconder mudanças reais de estado e sem criar acoplamento com transporte externo ou execução.
