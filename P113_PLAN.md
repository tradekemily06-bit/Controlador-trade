# P113 — arquitetura multi-corretora

Cria uma fronteira de adaptadores para corretoras. O núcleo do ecossistema não conhece APIs, autenticação ou detalhes de uma corretora. Uma corretora é selecionada somente por configuração externa e o registro permite múltiplos adaptadores.