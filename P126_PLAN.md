# P126 — Validação de segurança pré-REAL

## Objetivo
Consolidar uma barreira independente antes de qualquer adapter de corretora real.

## Requisitos
- configuração padrão DEMO com `real_enabled=False`;
- REAL exige habilitação explícita;
- sessão não autenticada bloqueia;
- AGUARDAR não gera ordem;
- ordem inválida falha fechado;
- resultado aceito sem `external_id` permanece ambíguo;
- UNKNOWN/RESERVED não pode ser reenviado automaticamente;
- PENDING/UNKNOWN nunca gera retry automático;
- dados de mercado inválidos não entram no núcleo;
- simulador P125 não usa rede;
- nenhuma camada de aprendizado/notícias/IA pode habilitar REAL.

P126 é uma validação de segurança, não uma autorização para operar dinheiro real.
