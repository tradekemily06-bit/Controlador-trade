# P26 — Execution Intent Contract

## Objetivo
Criar uma fronteira imutável entre decisão/risco e qualquer adaptador de execução, sem conectar corretoras e sem enviar ordens.

## Regras
- uma intenção de execução deve identificar a operação de forma única;
- símbolo, direção, valor, duração e modo devem ser explícitos;
- somente `DEMO` pode ser aceito nesta etapa;
- intenção inválida deve falhar fechado;
- o contrato não conhece broker, API, rede ou credenciais;
- criar uma intenção não executa nem agenda uma ordem.

## Critério de encerramento
P26 é considerado concluído quando o núcleo puder representar uma intenção de execução validada e imutável, independente de corretora, e houver testes cobrindo entradas inválidas, REAL bloqueado e ausência de efeitos colaterais.
