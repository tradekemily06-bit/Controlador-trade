from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.self_repair_policy import RepairRequest, SelfRepairPolicy  # noqa: E402


def _bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise argparse.ArgumentTypeError("valor booleano deve ser true ou false")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Avalia autorização segura de autorreparo.")
    parser.add_argument("--action", required=True)
    parser.add_argument("--attempts-used", type=int, required=True)
    parser.add_argument("--max-attempts", type=int, required=True)
    for name in (
        "local-only", "reversible", "deterministic", "prevalidated",
        "external-side-effects", "touches-execution-state",
        "requires-human-supervision", "cooldown-elapsed",
        "maintenance-lock-clear", "execution-quiescent",
    ):
        parser.add_argument(f"--{name}", type=_bool, required=True)
    args = parser.parse_args(argv)
    if args.action in {"start_mt5_terminal", "restart_controller", "restart_mt5_terminal"}:
        provider = os.environ.get("CONTROLADOR_EXECUTION_PROVIDER", "")
        real_flags = (
            "CONTROLADOR_REAL_EXPLICITLY_ENABLED",
            "CONTROLADOR_REAL_EXECUTION_ALLOWED",
            "CONTROLADOR_REAL_AUDIT_VERIFIED",
            "CONTROLADOR_REAL_RISK_APPROVED",
        )
        if provider != "ic_markets_mt5_demo" or any(os.environ.get(name, "false").strip().lower() != "false" for name in real_flags):
            print(json.dumps({
                "allowed": False,
                "decision": "ALERT_AND_BLOCK",
                "reason": "provider DEMO ou bloqueio REAL não foi confirmado pelo ambiente do supervisor",
            }, ensure_ascii=False))
            return 2
    values = vars(args)
    values = {key.replace("-", "_"): value for key, value in values.items()}
    authorization = SelfRepairPolicy.evaluate(RepairRequest(**values))
    print(json.dumps({
        "allowed": authorization.allowed,
        "decision": authorization.decision.value,
        "reason": authorization.reason,
    }, ensure_ascii=False))
    return 0 if authorization.allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
