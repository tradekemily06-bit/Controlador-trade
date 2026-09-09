# P45 — Contrato de auditoria do ciclo automatizado

## Objetivo
Criar um registro factual e imutável do handoff automatizado, preservando a ligação entre ciclo, intenção DEMO e admissão P43 sem persistência ou efeitos externos.

## Regras
- consumir somente um handoff P44 válido;
- registrar ciclo, request_id, símbolo, direção, modo e instante da intenção;
- não inferir resultado, lucro, qualidade ou sucesso de execução;
- não executar, persistir ou enviar dados externamente;
- rejeitar REAL e entradas inválidas;
- resultado imutável e determinístico.

## Critério de encerramento
Existe um contrato testado que representa o fato de um ciclo ter alcançado o handoff DEMO, deixando rastreabilidade estrutural para etapas posteriores sem confundir intenção com execução ou resultado.
