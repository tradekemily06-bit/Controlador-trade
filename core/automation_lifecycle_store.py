from __future__ import annotations

import json
from pathlib import Path

from core.p46_automation_lifecycle import AutomationLifecycle, AutomationLifecycleState


class AutomationLifecycleStore:
    """Durable store for automation lifecycle snapshots.

    This stores lifecycle state only; it never authorizes or dispatches trades.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, AutomationLifecycle]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            items = payload.get("cycles", {}) if isinstance(payload, dict) else {}
            if not isinstance(items, dict):
                return {}
        except (OSError, json.JSONDecodeError):
            return {}

        result: dict[str, AutomationLifecycle] = {}
        for cycle_id, state in items.items():
            try:
                cid = str(cycle_id).strip()
                lifecycle_state = AutomationLifecycleState(str(state))
                if cid:
                    result[cid] = AutomationLifecycle(cid, lifecycle_state)
            except (TypeError, ValueError):
                continue
        return result

    def save(self, lifecycle: AutomationLifecycle) -> None:
        if not isinstance(lifecycle, AutomationLifecycle):
            raise ValueError("lifecycle is required")
        if not isinstance(lifecycle.cycle_id, str) or not lifecycle.cycle_id.strip():
            raise ValueError("cycle_id is required")
        if not isinstance(lifecycle.state, AutomationLifecycleState):
            raise ValueError("invalid lifecycle state")

        current = self.load()
        current[lifecycle.cycle_id] = lifecycle
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "cycles": {
                cycle_id: item.state.value
                for cycle_id, item in sorted(current.items())
            },
        }
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)
