# Controlador Trading — ponte MT5 em ambiente remoto

## Objetivo

Permitir que o usuário opere o ecossistema pelo celular sem precisar manter um computador pessoal ligado.

O pacote oficial `MetaTrader5` para Python comunica-se diretamente com um terminal MetaTrader 5; portanto, o terminal precisa existir no mesmo ambiente operacional do processo Python que fará a execução. O ecossistema não deve tentar falar diretamente com o aplicativo MT5 Android.

## Arquitetura escolhida

```text
Celular
  │
  ▼
Controlador Trading
  │  API autenticada / somente DEMO
  ▼
Ponte MT5 remota
  │
  ├── terminal MetaTrader 5
  └── pacote MetaTrader5/Python
  │
  ▼
IC Markets — conta DEMO
```

A ponte é uma fronteira operacional. Ela não contém lógica de sinal, score, risco ou estratégia.

## Regras obrigatórias

1. A primeira fase é exclusivamente DEMO.
2. Credenciais nunca ficam no GitHub, no código-fonte ou no chat.
3. O serviço remoto deve confirmar conta DEMO antes de qualquer ordem.
4. `AGUARDAR` nunca gera ordem.
5. `order_check()` deve preceder `order_send()`.
6. A resposta deve carregar um identificador externo quando o broker confirmar a ordem.
7. Falha de saúde, autenticação, símbolo, cotação ou confirmação deve bloquear a execução.
8. REAL permanece desabilitado.
9. Depois de uma ordem DEMO controlada, a posição deve ser reconciliada e encerrada explicitamente.
10. A ponte não deve ser confundida com o VPS nativo do MetaTrader: o pacote Python precisa acessar o terminal MT5 que está no ambiente onde o Python roda.

## Ambiente remoto

Pode ser uma VM/VPS Windows compatível com MT5. Isso não exige que o usuário tenha um computador próprio: o terminal roda na nuvem e o celular continua sendo a interface de acompanhamento/controle.

O VPS específico, preço e elegibilidade devem ser confirmados no momento da contratação. A IC Markets informa que oferece VPS e plataformas Windows, Web Browser e Android, mas as condições de VPS podem depender de elegibilidade e termos vigentes.

## Sequência de ativação

1. Disponibilizar o ambiente remoto compatível.
2. Instalar MetaTrader 5 no ambiente remoto.
3. Entrar somente na conta IC Markets DEMO.
4. Instalar `MetaTrader5` para Python.
5. Executar o health check somente leitura.
6. Confirmar servidor, conta DEMO, terminal conectado e símbolo.
7. Testar leitura de cotação.
8. Testar `order_check()` sem enviar ordem.
9. Habilitar uma única ordem DEMO de volume mínimo compatível.
10. Confirmar `order_send()` e o identificador externo.
11. Reconciliar a posição com o estado do MT5.
12. Encerrar a posição DEMO.
13. Reconciliar novamente.
14. Manter REAL desabilitado.

## Segurança

A ponte não recebe senha através da API do ecossistema. A sessão da conta deve ser configurada no terminal remoto por um mecanismo seguro de ambiente/segredo. Logs não podem registrar senha, token ou dados de autenticação.
