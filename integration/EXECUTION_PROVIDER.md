# DEMO execution provider selection

The application remains PAPER by default.

To explicitly select the IC Markets MT5 DEMO provider, set:

`CONTROLADOR_EXECUTION_PROVIDER=ic_markets_mt5_demo`

Optionally select a symbol with:

`CONTROLADOR_EXECUTION_SYMBOL=EURUSD`

The integration factory returns a broker-agnostic DEMO execution port. It does **not** return the concrete MT5 adapter or expose a registry lookup path. The adapter accepts only DEMO execution and the global REAL path remains blocked.

The adapter does not store credentials. The MT5 terminal/runtime remains responsible for its own authenticated session.

Any unsupported provider value—including `real`/`REAL`—fails during application construction instead of silently falling back to another executor.
