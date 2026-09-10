# MT5 DEMO health preflight

`check_mt5_demo_health()` is a read-only preflight for a compatible MT5 runtime. It initializes the terminal, reads account information, verifies DEMO mode, and always shuts down the runtime. It never calls order_check or order_send.
