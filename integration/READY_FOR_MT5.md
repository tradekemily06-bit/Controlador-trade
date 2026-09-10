# Pronto para validação MT5

O software mantém a execução bloqueada até que a validação operacional externa seja realizada em um runtime com terminal MetaTrader 5 compatível.

A ordem de validação é deliberadamente curta e segura: health/read-only → conta DEMO → símbolo/cotação → `order_check()` → ordem DEMO controlada → confirmação → fechamento → reconciliação.

Não há credenciais no repositório e nenhuma validação externa é considerada concluída sem evidência do runtime.
