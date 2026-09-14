# Auditoria profunda — registro de itens guardados

Este registro existe para impedir que qualquer requisito seja perdido quando uma dependência externa, configuração, aprovação ou outra fase impedir a conclusão imediata.

## Itens guardados

| ID | Item | Estado | Próxima ação |
|---|---|---|---|
| DEF-01 | Data plane durável tenant+subject scoped | PENDENTE | implementar/validar provider de produção e integrar HTTP → serviço → storage |
| DEF-02 | `/api/outcome` com propriedade confiável | PENDENTE | carregar decisão no escopo confiável antes de alterar outcome |
| DEF-03 | Memória/estatísticas/preferências/notificações por usuário/tenant | PENDENTE | eliminar estado global como fonte de verdade em SaaS |
| DEF-04 | Learning por usuário/tenant e provenance confiável | PENDENTE | ligar identidade e proveniência administrativa ao data plane |
| DEF-05 | PointValueEngine dinâmico | PRÓXIMO | implementar normalização ponto/tick/pip + conversão monetária + frescor/proveniência |
| DEF-06 | Revisão do `margin_required` da alavancagem | PENDENTE | usar modelo compatível com especificação real do instrumento/broker; evitar dupla contagem |
| DEF-07 | Currículo profissional sênior com provenance/validação/testes | PENDENTE | transformar currículo existente em matriz de conhecimento verificável |
| DEF-08 | Custo de replay sem teto funcional | PENDENTE | proteger CPU/memória/tempo/armazenamento/concorrência sem limitar funcionalidade arbitrariamente |
| DEF-09 | Rate limit compartilhado multi-réplica | PENDENTE | mover autoridade de anti-abuso para mecanismo compartilhado de produção |
| DEF-10 | Auditoria/retention compartilhada multi-réplica | PENDENTE | definir armazenamento durável centralizado |
| DEF-11 | Autenticação/sessão/RBAC/CSRF de produção | PENDENTE | integrar provider confiável e validar toda a cadeia |
| DEF-12 | News provider real | PENDENTE | conectar fonte confiável sem transformar notícia em autoridade de execução |
| DEF-13 | REAL | BLOQUEADO | só revisar após todos os gates de produção comprovados |
| DEF-14 | cTrader Open API | DEFERIDO / NÃO BLOQUEANTE | retomar quando a integração for útil; não parar o restante do ecossistema |
| DEF-15 | Atualização contínua do Modo de Usar/notificações | CONTÍNUO | cada recurso novo deve ser localizável e receber alerta quando material |

## Regras

1. `PENDENTE` não significa esquecido; significa explicitamente preservado para retomada.
2. `DEFERIDO` não significa descartado.
3. Nenhum item pode ser marcado como RESOLVIDO sem código/teste/documentação compatíveis.
4. Dependências externas devem bloquear apenas o que realmente depende delas.
5. Não criar limites funcionais artificiais para fechar auditoria.
6. Não remover itens deste arquivo; alterar o estado e registrar a nova decisão quando concluídos.
7. Ao finalizar uma fase, reavaliar este registro antes de avançar para a seguinte.
