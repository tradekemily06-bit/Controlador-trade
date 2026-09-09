# P125 — Validação integrada DEMO/Sandbox

## Objetivo
Validar o fluxo completo da primeira integração sem usar uma corretora real.

## Cenários obrigatórios
- ordem aceita com `external_id`;
- ordem rejeitada;
- resposta ambígua/UNKNOWN;
- indisponibilidade/desconexão;
- repetição do mesmo `request_id` sem duplicar ordem;
- consulta posterior por `external_id`;
- reconciliação terminal e não terminal.

## Regra
P125 usa somente adapter/simulador controlado. Nenhuma chamada externa é feita e nenhum estado REAL é habilitado.
