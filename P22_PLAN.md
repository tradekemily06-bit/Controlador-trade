# P22 — Configuration and contract validation

Objetivo: centralizar a configuração de uma sessão do runtime em um contrato imutável e validado.

Inclui:
- symbol/timeframe obrigatórios;
- amount e duration positivos e finitos/inteiros;
- modo DEMO como padrão;
- rejeição explícita de REAL nesta etapa;
- normalização de caminhos persistentes;
- testes de entradas inválidas e imutabilidade.

Não altera estratégia nem conecta corretoras.
