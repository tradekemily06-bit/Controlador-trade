The application uses IC Markets MT5 DEMO as its canonical default executor.

The provider factory still accepts `paper` as an explicit isolated/test provider. To explicitly select IC Markets MT5 DEMO, set:

`CONTROLADOR_EXECUTION_PROVIDER=ic_markets_mt5_demo`

Optionally select a symbol with:

`CONTROLADOR_EXECUTION_SYMBOL=EURUSD`

The adapter does not store credentials. The MT5 terminal/runtime remains responsible for its own authenticated session. The adapter itself accepts only DEMO execution and the global REAL path remains blocked.

Any unsupported provider value fails during application construction instead of silently falling back to another executor.
