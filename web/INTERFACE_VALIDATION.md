# Validação da interface

Checklist da interface responsiva do Controlador Trading.

## Cobertura automatizada

`test_web_interface.py` verifica:

- carregamento do dashboard HTML;
- presença das seções Painel, Análise, Replay, Memória, Risco e Conexões;
- disponibilidade dos endpoints usados pela interface;
- estado seguro de simulação/DEMO;
- superfície REAL controlada, com estado ao vivo, preparação e confirmação humana;
- resposta funcional do endpoint de análise.

## Validação manual

1. Iniciar `python app.py`.
2. Abrir `http://localhost:8000` no notebook.
3. Testar Análise, Replay, Memória, Risco e Configurações.
4. Confirmar `DEMO_VALIDADO` e verificar o painel `REAL controlado`: ele deve permanecer bloqueado quando qualquer barreira estiver ausente e só permitir preparação/confirmação quando o runtime estiver admitido.
5. Depois testar a mesma interface pelo celular na mesma rede.

A validação manual continua necessária porque os testes automatizados não substituem a verificação visual e de responsividade em dispositivos reais.
