"""Read-only context assembly for the Controlador Trading assistant.

Only explicit, low-sensitivity fields are sent to the external model provider. Pending foreign items are represented by owner-scoped counts only.
This module does not execute trades, change settings, move funds, or infer tax outcomes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from finance.fiscal_taxonomy import fiscal_classification_catalog


def _iso_date(value: Any) -> str:
    if not isinstance(value, str) or len(value) != 10:
        return ""
    candidate = value[:10]
    try:
        datetime.strptime(candidate, "%Y-%m-%d")
    except ValueError:
        return ""
    return candidate


def _safe_currency_codes(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return sorted({
        item for item in (str(code).upper() for code in value)
        if len(item) == 3 and item.isascii() and item.isalpha()
    })[:10]


def _count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def _decision_summary(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    # Exclude decision IDs, symbols, reasons and any free-form/user-provided text.
    return {
        key: item[key]
        for key in ("created_at", "signal", "score", "confirmed", "outcome")
        if key in item and isinstance(item[key], (str, int, float, bool, type(None)))
    }


def _risk_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"available": False}
    limits = value.get("configured_limits")
    safe_limits = {}
    if isinstance(limits, dict):
        for key in ("daily_loss_limit", "max_operations", "max_consecutive_losses"):
            item = limits.get(key)
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                safe_limits[key] = item
    return {
        "available": True,
        "allowed": bool(value.get("allowed", False)),
        "configured_limits": safe_limits,
    }


def _operations_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"available": False}
    execution = value.get("execution") if isinstance(value.get("execution"), dict) else {}
    reconciliation = value.get("reconciliation") if isinstance(value.get("reconciliation"), dict) else {}
    recovery = value.get("recovery") if isinstance(value.get("recovery"), dict) else {}
    kill = value.get("kill_switch") if isinstance(value.get("kill_switch"), dict) else {}
    health = value.get("runtime_health") if isinstance(value.get("runtime_health"), dict) else {}
    market = value.get("market_data") if isinstance(value.get("market_data"), dict) else {}
    # Do not forward request IDs, free-form messages/reasons, supervisor payloads,
    # broker symbols, timeframes, or other arbitrary nested runtime data.
    return {
        "available": True,
        "execution": {
            "allowed": False,
            "mode": str(execution.get("mode", "UNKNOWN"))[:24],
            "state": str(execution.get("state", "UNKNOWN"))[:32],
            "real": "DISABLED",
        },
        "reconciliation": {
            "state": str(reconciliation.get("state", "UNKNOWN"))[:32],
            "pending_count": len(reconciliation.get("pending_request_ids", [])) if isinstance(reconciliation.get("pending_request_ids", []), list) else 0,
            "unknown_count": len(reconciliation.get("unknown_request_ids", [])) if isinstance(reconciliation.get("unknown_request_ids", []), list) else 0,
        },
        "recovery": {
            "state": str(recovery.get("state", "UNKNOWN"))[:32],
            "can_resume": bool(recovery.get("can_resume", False)),
        },
        "kill_switch": {
            "state": str(kill.get("state", "UNKNOWN"))[:24],
            "enabled": bool(kill.get("enabled", False)),
        },
        "runtime_health": {
            "state": str(health.get("state", "UNKNOWN"))[:24],
            "ledger_entries": _count(health.get("ledger_entries")),
            "pending_executions": _count(health.get("pending_executions")),
            "unknown_executions": _count(health.get("unknown_executions")),
        },
        "market_data": {
            "health": str(market.get("health", "UNKNOWN"))[:24],
            "safe_for_analysis": bool(market.get("safe_for_analysis", False)),
            "candle_count": _count(market.get("candle_count")),
            "gap_count": _count(market.get("gap_count")),
            "stale": market.get("stale") if isinstance(market.get("stale"), bool) else None,
        },
    }


def _statistics_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"available": False}
    safe = {}
    for key in ("total", "total_decisions", "actionable", "wins", "losses", "draws", "open", "win_rate"):
        item = value.get(key)
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            safe[key] = item
    periods = value.get("periods")
    if isinstance(periods, dict):
        safe["periods"] = {}
        for period in ("daily", "weekly", "monthly", "day", "week", "month", "year"):
            row = periods.get(period)
            if isinstance(row, dict):
                safe["periods"][period] = {
                    key: row[key] for key in ("total", "actionable", "wins", "losses", "draws", "open", "win_rate")
                    if key in row and isinstance(row[key], (int, float)) and not isinstance(row[key], bool)
                }
    safe["available"] = True
    return safe


def _fiscal_periods(value: Any) -> dict[str, dict[str, Any]]:
    """Allow only fixed period keys, ISO date bounds, counts and numeric aggregates."""
    safe: dict[str, dict[str, Any]] = {}
    if not isinstance(value, dict):
        return safe
    for period in ("day", "week", "month", "year"):
        row = value.get(period)
        if not isinstance(row, dict):
            continue
        item: dict[str, Any] = {}
        for key in ("start", "end"):
            raw = row.get(key)
            if isinstance(raw, str) and len(raw) >= 10:
                candidate = raw[:10]
                try:
                    datetime.strptime(candidate, "%Y-%m-%d")
                    item[key] = candidate
                except ValueError:
                    pass
        if "entries" in row:
            item["entries"] = _count(row.get("entries"))
        for key in ("realized_result_brl", "reserve_amount_brl"):
            raw = row.get(key)
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                item[key] = raw
        safe[period] = item
    return safe


def _fiscal_reserve_semantics(value: Any) -> dict[str, Any]:
    """Never forward free-form semantic descriptions from fiscal service data."""
    # These are application-owned invariants, not claims copied from fiscal
    # service data. Always emit the fixed safe contract, even if the service
    # omits or forges semantic fields.
    return {
        "kind": "PLANNING_ESTIMATE_ONLY",
        "tax_liability_confirmed": False,
        "monthly_tax_assessment": False,
        "monthly_loss_offsets_calculated": False,
        "irrf_credits_calculated": False,
        "positive_entry_only": True,
    }


def collect_read_only_context(service: Any, fiscal_reserve: Any, fiscal_owner_id: str, fiscal_pending_queue: Any = None, fiscal_domestic_pending_queue: Any = None) -> dict[str, Any]:
    """Build a compact, privacy-filtered snapshot for an assistant response."""
    if service is None or fiscal_reserve is None:
        raise ValueError("serviço do ecossistema e Reserva Fiscal são obrigatórios")

    status = service.system_status()
    risk = service.risk_status()
    observability = service.operational_observability()
    statistics = service.statistics()
    fiscal = fiscal_reserve.summary(fiscal_owner_id)
    fiscal_context: dict[str, Any] = {
        "name": "Reserva Fiscal",
        "currency": "BRL",
    }
    as_of = fiscal.get("as_of") if isinstance(fiscal, dict) else None
    if isinstance(as_of, str) and len(as_of) >= 10:
        try:
            fiscal_context["as_of"] = datetime.strptime(as_of[:10], "%Y-%m-%d").date().isoformat()
        except ValueError:
            pass
    total_reserved = fiscal.get("total_reserved_brl") if isinstance(fiscal, dict) else None
    if isinstance(total_reserved, (int, float)) and not isinstance(total_reserved, bool):
        fiscal_context["total_reserved_brl"] = total_reserved
    if isinstance(fiscal, dict):
        fiscal_context["categories"] = fiscal.get("categories", {}) if isinstance(fiscal.get("categories"), dict) else {}
        fiscal_context["periods"] = _fiscal_periods(fiscal.get("periods"))
        fiscal_context["reserve_semantics"] = _fiscal_reserve_semantics(fiscal.get("reserve_semantics"))
        # Do not send arbitrary service-provided limitation text to the model.
        fiscal_context["limitations"] = [
            "Estimativa de planejamento; não representa imposto apurado ou devido.",
            "Compensações fiscais e créditos de IRRF não são calculados.",
            "Categorias sem regra validada permanecem pendentes e fora dos totais.",
        ]
    # The legacy foreign category may still carry a historical generic rate
    # (15%). Never forward that rate to the external assistant as tax guidance.
    categories = fiscal_context.get("categories")
    if isinstance(categories, dict):
        # Forward only aggregate fields needed for planning. Never pass ledger
        # notes, references, or future free-form fields to the external model.
        safe_categories: dict[str, dict[str, Any]] = {}
        for category, item in categories.items():
            if not isinstance(category, str) or not isinstance(item, dict):
                continue
            if category not in {"BR_DAY_TRADE", "FOREIGN_FINANCIAL_ASSET"}:
                continue
            if category.startswith("FOREIGN_"):
                # Foreign categories remain classification-only. Legacy rows
                # are visible as counts, never as taxable results or reserves.
                safe_categories[category] = {
                    "entries": _count(item.get("entries")),
                    "realized_result_brl": 0.0,
                    "reserve_amount_brl": 0.0,
                    "classification_status": "PENDING_CLASSIFICATION",
                    "rate_available": False,
                }
                continue
            safe_item = {"entries": _count(item.get("entries"))}
            for key in ("rate", "realized_result_brl", "reserve_amount_brl"):
                value = item.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    safe_item[key] = value
            safe_categories[category] = safe_item
        fiscal_context["categories"] = safe_categories
    pending_context = {"available": False, "included_in_totals": False}
    if fiscal_pending_queue is not None:
        try:
            pending_summary = fiscal_pending_queue.summary(fiscal_owner_id)
            pending_context = {
                "available": True,
                "total": _count(pending_summary.get("total")),
                "realized_results": _count(pending_summary.get("realized_results")),
                "asset_amounts": _count(pending_summary.get("asset_amounts")),
                "currencies": _safe_currency_codes(pending_summary.get("currencies", [])),
                "periods": {
                    str(period): {
                        "start": _iso_date(values.get("start")),
                        "end": _iso_date(values.get("end")),
                        "total": _count(values.get("total")),
                        "realized_results": _count(values.get("realized_results")),
                        "asset_amounts": _count(values.get("asset_amounts")),
                    }
                    for period, values in pending_summary.get("periods", {}).items()
                    if period in {"day", "week", "month", "year"} and isinstance(values, dict)
                },
                "as_of": _iso_date(pending_summary.get("as_of")),
                "classification_status": "PENDING_CLASSIFICATION",
                "included_in_totals": False,
                "reserve_calculated": False,
            }
        except Exception:
            pending_context = {"available": False, "included_in_totals": False}
    fiscal_context["foreign_pending"] = pending_context
    domestic_pending_context = {"available": False, "included_in_totals": False}
    if fiscal_domestic_pending_queue is not None:
        try:
            domestic_summary = fiscal_domestic_pending_queue.summary(fiscal_owner_id)
            domestic_pending_context = {
                "available": True,
                "total": _count(domestic_summary.get("total")),
                "periods": {
                    str(period): {
                        "start": _iso_date(values.get("start")),
                        "end": _iso_date(values.get("end")),
                        "total": _count(values.get("total")),
                        "results": _count(values.get("results")),
                    }
                    for period, values in domestic_summary.get("periods", {}).items()
                    if period in {"day", "week", "month", "year"} and isinstance(values, dict)
                },
                "as_of": _iso_date(domestic_summary.get("as_of")),
                "classification_status": "PENDING_CLASSIFICATION",
                "included_in_totals": False,
                "reserve_calculated": False,
            }
        except Exception:
            domestic_pending_context = {"available": False, "included_in_totals": False}
    fiscal_context["domestic_pending"] = domestic_pending_context
    recent_decisions = service.memory_view(limit=5)

    components = status.get("components", {})
    safe_components = {}
    if isinstance(components, dict):
        for key, value in components.items():
            if isinstance(value, (str, int, float, bool)):
                safe_components[str(key)[:64]] = str(value)[:48] if isinstance(value, str) else value

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "sources": ["system_status", "risk_status", "operational_observability", "statistics", "fiscal_reserve", "fiscal_pending_queue_summary", "fiscal_domestic_pending_queue_summary", "recent_decisions"],
        "system": {
            "mode": str(status.get("mode", "UNKNOWN"))[:24],
            "execution_allowed": False,
            "real": "DESABILITADO",
            "health": str(status.get("health", "UNKNOWN"))[:24],
            "components": safe_components,
        },
        "risk": _risk_summary(risk),
        "operations": _operations_summary(observability),
        "statistics": _statistics_summary(statistics),
        "fiscal_reserve": fiscal_context,
        "fiscal_classification_catalog": fiscal_classification_catalog(),
        "recent_decisions": [_decision_summary(item) for item in recent_decisions if isinstance(item, dict)][-5:],
        "assistant_safety": {
            "read_only": True,
            "may_execute_orders": False,
            "may_enable_real": False,
            "may_move_money": False,
            "tax_estimates_are_not_tax_assessments": True,
            "unknown_data_must_be_reported_as_unavailable": True,
        },
    }
