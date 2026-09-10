# Controlador Trading — status de conclusão

## Estado atual

O núcleo técnico e as fronteiras de execução do projeto estão concluídos no `main`. A integração escolhida para a primeira validação operacional é **IC Markets MT5 DEMO**.

A conta DEMO da IC Markets já pode ser conectada ao aplicativo MT5 no celular, mas a validação do adapter Python ainda depende de um **terminal MetaTrader 5 compatível com o pacote oficial MetaTrader5**. Essa etapa é operacional e não exige alterar o núcleo do projeto.

## Concluído

- Núcleo de decisão independente de corretora/plataforma.
- Fluxo dados → análise → score/filtros → decisão → risco → execução → auditoria.
- Contratos de dados de mercado e execução.
- Gateway de execução com kill switch, bloqueio de duplicidade e comportamento fail-closed.
- Persistência/controle de estados de execução e tratamento explícito de `UNKNOWN`.
- Reconciliação externa.
- Validações de segurança antes de qualquer uso REAL.
- Boundary cTrader DEMO/OAuth preservada como integração futura, sem bloquear o projeto.
- Boundary específica para IC Markets cTrader preservada como futura.
- Adapter IC Markets MT5 DEMO.
- Preflight somente leitura para confirmar disponibilidade e conta DEMO.
- Testes de segurança do adapter e do preflight.
- Runbook para a primeira conexão MT5 DEMO.
- CI configurada para executar a suíte de testes e compilação do projeto.
- Nenhuma credencial de conta deve ser persistida no repositório.

## Pendência operacional real

Ainda não foi comprovada uma execução do adapter Python contra um terminal MT5 real conectado à conta IC Markets DEMO. O MT5 Android conectado no celular confirma a conta/plataforma do lado do usuário, mas não substitui o terminal MT5 que o pacote Python usa para comunicação entre processos.

Quando houver acesso a um ambiente compatível, a sequência será:

1. iniciar o terminal MT5;
2. confirmar conta IC Markets DEMO;
3. executar o preflight somente leitura;
4. confirmar símbolo e cotação;
5. validar volume mínimo/step;
6. executar `order_check()`;
7. somente se aprovado, enviar uma ordem DEMO controlada;
8. registrar o identificador externo;
9. reconciliar com a auditoria local;
10. fechar a posição DEMO explicitamente;
11. reconciliar novamente.

Nenhuma senha, token ou credencial deve ser colocada no GitHub ou no chat.

## REAL

REAL permanece bloqueado. A existência do adapter DEMO não autoriza execução financeira real. A passagem para REAL exige validação operacional, reconciliação e critérios de segurança adicionais.

## Regra de encerramento

Não criar novas etapas apenas para prolongar o projeto. A parte de software necessária para a integração IC Markets MT5 DEMO está encerrada. O único bloqueio restante desta integração é a validação operacional no terminal MT5 compatível. Defeitos encontrados nessa validação devem gerar correções específicas; não devem gerar novos P-steps artificiais.
