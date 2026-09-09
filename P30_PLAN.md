# P30 — DEMO Execution Readiness Boundary

## Objetivo
Fechar o bloco P26–P30 com uma avaliação única, somente leitura, que determine se o sistema está pronto para uma execução DEMO controlada.

## Regras
- READY significa somente `DEMO`;
- REAL permanece explicitamente bloqueado;
- kill switch ativo bloqueia;
- mercado não íntegro bloqueia;
- recuperação não resolvida bloqueia;
- intenção ausente ou inválida não pode ser considerada pronta;
- nenhuma ordem é enviada pelo readiness check.

## Critério de encerramento
O núcleo possui uma fronteira final de prontidão DEMO que combina os contratos de segurança existentes sem executar, agendar ou conectar diretamente a uma corretora.
