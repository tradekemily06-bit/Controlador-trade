# P40 — Orçamento de risco operacional

## Objetivo
Adicionar uma fronteira determinística para orçamento diário de risco, complementando o limite por operação do P39 sem executar ordens ou alterar o estado operacional.

## Regras
- validar perda acumulada, quantidade de operações e limites configurados;
- calcular perda projetada de forma explícita;
- bloquear quando o orçamento ou o limite de operações for excedido;
- valores inválidos ou não finitos falham fechando;
- resultado imutável e somente leitura;
- não realizar retry, replay, rede ou execução;
- REAL continua bloqueado.

## Critério de encerramento
Existe uma avaliação testada de orçamento de risco que pode ser consumida por camadas superiores antes da operação, sem duplicar execução ou alterar o runtime.
