# Controlador Trading — fechamento técnico MT5 DEMO

## Estado atual

O núcleo do Controlador Trading e suas fronteiras de dados, decisão, risco, auditoria e execução segura estão implementados na `main`. A rota IC Markets via MetaTrader 5 foi adicionada como uma boundary de execução DEMO, sem acoplar o núcleo à corretora.

## Concluído

- Núcleo de decisão independente de corretora.
- Fluxo dados → análise → score/filtros → decisão → risco → execução → auditoria.
- Contratos de dados de mercado e execução.
- Gateway de execução com kill switch, bloqueio de duplicidade e comportamento fail-closed.
- Persistência/controle de estados e tratamento explícito de `UNKNOWN`.
- Reconciliação externa.
- Validações de segurança antes de qualquer uso REAL.
- Adaptador cTrader DEMO preservado como integração futura.
- Boundary IC Markets MT5 DEMO isolada atrás de `BrokerAdapter`.
- Bloqueio explícito de `REAL` e `AGUARDAR` no adapter MT5.
- Verificação de conta DEMO antes de qualquer ordem.
- `order_check()` obrigatório antes de `order_send()`.
- Testes portáteis para as principais barreiras de segurança do adapter.
- Dependência `MetaTrader5` isolada em `requirements-mt5.txt`, sem quebrar a suíte Linux/CI do núcleo.
- Nenhuma credencial deve ser persistida no repositório.

## Limite operacional conhecido

A boundary de software está implementada e testada com runtime simulado. A conexão operacional real com uma conta IC Markets DEMO ainda precisa ser executada em um ambiente compatível com o terminal MetaTrader 5. A documentação do adapter registra essa exigência.

O ambiente Codespace/Linux não deve ser tratado como prova de conexão MT5 real. Portanto, nenhuma ordem real ou alegação de execução em conta DEMO é feita a partir apenas dos testes automatizados.

## O que não deve ser feito agora

- Não liberar `ExecutionMode.REAL`.
- Não colocar credenciais no GitHub.
- Não transformar `duration_seconds` em uma falsa expiração MT5.
- Não misturar lógica de sinal, score ou risco dentro do adapter.
- Não esperar aprovação do cTrader para continuar o projeto.
- Não criar novas etapas artificiais apenas para prolongar o desenvolvimento.

## Encerramento técnico

Com a validação automatizada disponível e a boundary MT5 DEMO protegida, o projeto entra em **encerramento técnico**. O único passo externo restante para provar a integração operacional é executar o runtime Windows/MT5 com uma conta DEMO válida e observar o fluxo controlado de execução/reconciliação. Defeitos encontrados nesse teste devem ser corrigidos; fora isso, não há motivo arquitetural para reescrever o núcleo.
