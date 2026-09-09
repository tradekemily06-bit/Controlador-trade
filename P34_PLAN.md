# P34 — Fronteira de entrega de alertas

## Objetivo
Separar a geração determinística de alertas operacionais (P33) da entrega em canais externos, criando um contrato seguro para consumo por interface, logs, webhook, push ou e-mail sem acoplar o núcleo a qualquer transporte.

## Regras
- consumir somente `OperationalAlertReport` já produzido por P33;
- entrega deve ser uma fronteira explícita e broker-agnóstica;
- o núcleo não abre rede, envia e-mail, push ou webhook;
- cada alerta é encaminhado no máximo uma vez por chamada de dispatch;
- ordem dos alertas permanece determinística;
- falha de um destino não deve alterar o relatório de origem;
- destinos inválidos devem falhar de forma explícita e segura;
- o contrato deve permitir adaptadores externos futuros sem alterar P33;
- não executar ordens, retry automático ou replay.

## Critério de encerramento
Existe uma fronteira de entrega testada que transforma `OperationalAlertReport` em mensagens destinadas a um sink abstrato, sem efeitos externos no núcleo e sem modificar os alertas originais.
