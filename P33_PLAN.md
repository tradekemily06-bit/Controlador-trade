# P33 — Alertas operacionais e monitoramento de segurança

## Objetivo
Transformar os sinais já existentes de observabilidade, integridade de mercado e prontidão em alertas operacionais determinísticos, sem acoplar o núcleo a e-mail, push, webhook ou corretora.

## Regras
- reutilizar `RuntimeHealthMonitor`, `MarketDataIntegrityReport` e `SafetyGateReport` existentes;
- alertas são somente leitura e não alteram estado;
- cada alerta possui código estável, severidade, mensagem e origem;
- estado `BLOCKED`, mercado `INVALID` ou entrada inválida gera alerta `CRITICAL`;
- `ATTENTION`, `PENDING`, `STALE` ou `GAP` gera alerta `WARNING`;
- estado totalmente saudável não gera alerta de incidente;
- não executar ordens, retry, replay ou notificações externas;
- saída determinística e fail-closed;
- não duplicar a observabilidade P21: P33 interpreta seus resultados como eventos operacionais acionáveis.

## Critério de encerramento
Existe uma fronteira de alertas operacionais testada que converte os estados de segurança já existentes em incidentes determinísticos, sem executar ou modificar o runtime e sem depender de um canal externo de notificação.
