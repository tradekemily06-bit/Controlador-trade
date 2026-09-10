# Boundary operacional

A conexão externa é deliberadamente separada do núcleo de decisão.

Antes de qualquer envio DEMO, o runtime deve confirmar:

- terminal MetaTrader 5 disponível;
- conta IC Markets em modo DEMO;
- símbolo selecionável e cotação disponível;
- volume válido para o símbolo;
- `order_check()` aprovado;
- resultado de `order_send()` explicitamente confirmado;
- identificador externo registrado para reconciliação.

Falha ou ambiguidade em qualquer ponto bloqueia o fluxo.
