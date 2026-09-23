from __future__ import annotations

import os
from pathlib import Path

from core.operational_runtime import build_operational_runtime
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter, ICMarketsMT5DemoConfig
from execution.ports import ExecutionAction, ExecutionMode, ExecutionRequest
from core.models import Signal


def main() -> None:
    adapter = ICMarketsMT5DemoAdapter(ICMarketsMT5DemoConfig())
    runtime = build_operational_runtime(
        Path(os.environ.get("CONTROLADOR_RUNTIME_DIR", ".runtime")),
        executor=adapter,
    )
    mt5 = adapter._module()
    if not mt5.initialize():
        print(f"MT5 indisponível: {mt5.last_error()}")
        return
    try:
        account = mt5.account_info()
        if account is None or not adapter._is_demo_account(account, mt5):
            print("BLOQUEADO: conta não confirmada como DEMO.")
            return
        positions = mt5.positions_get(symbol=adapter.config.symbol or "EURUSD") or ()
        candidates = [p for p in positions if getattr(p, "magic", None) == adapter.config.magic]
        if len(candidates) != 1:
            print(f"BLOQUEADO: esperado exatamente 1 posição do Controlador; encontrado={len(candidates)}")
            return
        position = candidates[0]
        is_buy = int(getattr(position, "type", -1)) == int(mt5.POSITION_TYPE_BUY)
        request_id = f"demo-close-{int(position.ticket)}"
        request = ExecutionRequest(
            symbol=str(position.symbol),
            signal=Signal.VENDA if is_buy else Signal.COMPRA,
            amount=float(position.volume),
            duration_seconds=1,
            mode=ExecutionMode.DEMO,
            request_id=request_id,
            action=ExecutionAction.CLOSE,
            position_id=int(position.ticket),
        )
        result = runtime.gateway.execute(request_id, request)
        print(f"CLOSE_STATUS={result.status.value}; MESSAGE={result.message}; DEMO_ONLY=True; REAL=False")
        if result.execution is not None:
            print(f"EXTERNAL_ID={result.execution.external_id}")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
