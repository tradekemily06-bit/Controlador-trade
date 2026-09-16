# Stage 3 — Production Readiness

## Estado

**Preparada estruturalmente, ainda não liberada.** Stage 3 só pode receber trabalho de produção depois que a matriz final da Stage 2 estiver verde.

## Dependências obrigatórias da Stage 2

Antes de qualquer expansão de produção:

1. fechar a origem/emissão da identidade privilegiada REAL;
2. fechar o binding `DecisionSnapshot.symbol -> ExecutionRequest.symbol` na fronteira REAL;
3. aplicar a política de frescor da decisão como barreira obrigatória também no caminho REAL;
4. validar reconstrução após restart, compatibilidade legada e ausência de side doors;
5. executar a matriz consolidada com CI verde, incluindo o run mais recente do workflow.

## Trabalho permitido enquanto Stage 2 fecha

Somente preparação que não aumenta a capacidade de execução REAL, como documentação de arquitetura, contratos de teste, observabilidade e especificações de integração DEMO/sandbox.

## Primeiro trabalho de produção após os gates

A primeira integração concreta continua sendo IC Markets MT5 DEMO, conforme `P127_PLAN.md`. O objetivo é validar disponibilidade, contrato comum, `order_check()`, execução controlada, external_id, reconciliação e auditoria em DEMO. Não há autorização para abrir REAL.

## Regra de segurança

Nenhum trabalho de Stage 3 pode contornar, enfraquecer ou substituir as barreiras da Stage 2. A habilitação REAL permanece uma decisão posterior, separada e explicitamente controlada.
