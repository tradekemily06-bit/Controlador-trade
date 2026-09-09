# P124 — Autenticação e sessão da corretora

## Objetivo
Criar uma fronteira segura para autenticação/sessão de adapters de corretora antes de qualquer integração concreta.

## Estados
- AUTHENTICATED
- EXPIRED
- REVOKED
- UNAVAILABLE
- UNKNOWN

Somente AUTHENTICATED libera o adapter para uso. Qualquer outro estado falha fechado.

## Invariantes
- credenciais não ficam hard-coded no núcleo;
- o contrato não persiste segredo/token;
- expiração, revogação e indisponibilidade bloqueiam operações;
- renovação/reautenticação pertence ao adapter;
- sessão não ativa REAL por si só;
- nenhuma chamada de rede pertence ao núcleo.
