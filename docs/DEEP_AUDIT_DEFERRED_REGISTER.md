# Auditoria profunda — registro de itens guardados

Este registro existe para impedir que qualquer requisito seja perdido quando uma dependência externa, configuração, aprovação ou outra fase impedir a conclusão imediata.

## Itens guardados

| ID | Item | Estado | Próxima ação |
|---|---|---|---|
| DEF-01 | Data plane durável tenant+subject scoped | BASE EXISTENTE / PENDENTE PROVIDER COMPARTILHADO | validar provider de produção e concluir integração HTTP → serviço → storage para deployment multi-réplica |
| DEF-02 | `/api/outcome` com propriedade confiável | BASE INTEGRADA / AUDITORIA CONTÍNUA | continuar verificando identidade confiável, carregamento scoped e concorrência |
| DEF-03 | Memória/estatísticas/preferências/notificações por usuário/tenant | PARCIALMENTE RESOLVIDO | manter fontes duráveis scoped e remover qualquer fonte global residual antes do SaaS multi-réplica |
| DEF-04 | Learning por usuário/tenant e provenance confiável | PARCIALMENTE RESOLVIDO | continuar auditando provenance administrativa e data plane de produção |
| DEF-05 | PointValueEngine dinâmico | IMPLEMENTADO / AUDITORIA CONTÍNUA | manter reconciliação fail-closed e revisar `margin_required` e integrações futuras por broker/instrumento |
| DEF-06 | Revisão do `margin_required` da alavancagem | PENDENTE | usar modelo compatível com especificação real do instrumento/broker; evitar dupla contagem |
| DEF-07 | Currículo profissional sênior com provenance/validação/testes | BASE AUDITÁVEL / VALIDAÇÃO CONTÍNUA | preencher evidências reais, fontes, versões, testes e ciclos de reavaliação |
| DEF-08 | Custo de replay sem teto funcional | EM VALIDAÇÃO | teto artificial removido; validar proteção por custo real, cancelamento, backpressure, armazenamento e respostas grandes |
| DEF-09 | Rate limit compartilhado multi-réplica | PENDENTE | mover autoridade de anti-abuso para mecanismo compartilhado de produção; deployment atual deve permanecer single-instance quando depender de limiter local |
| DEF-10 | Auditoria/retention compartilhada multi-réplica | PENDENTE | definir armazenamento durável centralizado |
| DEF-11 | Autenticação/sessão/RBAC/CSRF de produção | PENDENTE | integrar provider confiável e validar toda a cadeia |
| DEF-12 | News provider real | PENDENTE | conectar fonte confiável sem transformar notícia em autoridade de execução |
| DEF-13 | REAL | BLOQUEADO | só revisar após todos os gates de produção comprovados |
| DEF-14 | cTrader Open API | DEFERIDO / NÃO BLOQUEANTE | retomar quando a integração for útil; não parar o restante do ecossistema |
| DEF-15 | Atualização contínua do Modo de Usar/notificações | CONTÍNUO | cada recurso novo deve ser localizável e receber alerta quando material |
| DEF-16 | Política de limites e escala | DOCUMENTADO | aplicar a classificação Produto/Infraestrutura/Risco/Frescura/Observabilidade em cada novo limite |
| DEF-17 | Histórico de decisões sem teto de resposta | BASE RESOLVIDA / PAGINAÇÃO DE UI SEPARADA | manter ausência de teto funcional no repositório/provider e usar paginação explícita apenas para interfaces quando necessário |

## Regras

1. `PENDENTE` não significa esquecido; significa explicitamente preservado para retomada.
2. `DEFERIDO` não significa descartado.
3. Nenhum item pode ser marcado como RESOLVIDO sem código/teste/documentação compatíveis.
4. Dependências externas devem bloquear apenas o que realmente depende delas.
5. Não criar limites funcionais artificiais para fechar auditoria.
6. Não remover itens deste arquivo; alterar o estado e registrar a nova decisão quando concluídos.
7. Ao finalizar uma fase, reavaliar este registro antes de avançar para a seguinte.
8. `limit`, `MAX_*`, quotas e valores padrão devem ser classificados antes de serem considerados pendências ou resoluções; proteções de recurso não podem ser apresentadas como capacidade funcional.
