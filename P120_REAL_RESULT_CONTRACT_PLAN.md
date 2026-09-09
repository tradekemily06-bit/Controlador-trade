# P120 — Contrato de resultado REAL

## Objetivo
Fechar a fronteira entre o adapter de corretora e o núcleo REAL antes da integração com uma corretora concreta.

## Regras
- `ExecutionResult.accepted=True` sem `external_id` não pode ser tratado como aceite confirmado.
- Resultado aceito sem identificador externo é `UNKNOWN`, pois a ordem pode ter sido enviada e o sistema não possui referência confiável para reconciliação.
- Resultado rejeitado pode não possuir `external_id`.
- Nenhuma condição de resultado ambíguo pode provocar reenvio automático.
- A reconciliação é explícita e nunca reenvia a mesma ordem.
- O contrato continua independente de uma corretora específica.
- `REAL` continua bloqueado por padrão.

## Fora de escopo
- Conectar uma corretora.
- Implementar API, autenticação ou protocolo específico.
- Alterar estratégia, sinais ou gestão de risco.

## Critério de conclusão
O gateway deve distinguir aceite externo identificável de aceite ambíguo e possuir testes cobrindo o caso sem `external_id`.
