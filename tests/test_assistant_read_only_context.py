from assistant.read_only_context import collect_read_only_context


class FakeService:
    def system_status(self):
        return {
            "mode": "SIMULACAO",
            "execution_allowed": False,
            "real": "DESABILITADO",
            "health": "OK",
            "components": {"mt5_demo": "NOT_CONNECTED"},
        }

    def risk_status(self):
        return {"allowed": False, "reason": "dados insuficientes"}

    def operational_observability(self):
        return {"execution": {"allowed": False, "mode": "DEMO"}}

    def statistics(self):
        return {"total_decisions": 3, "win_rate": 0.0}

    def memory_view(self, limit=50):
        assert limit == 5
        return [{"decision_id": "d-1", "signal": "AGUARDAR"}]


class FakeFiscalReserve:
    def summary(self):
        return {"name": "Reserva Fiscal", "total_reserved_brl": 0.0, "history": []}


def test_context_is_read_only_and_contains_existing_module_summaries():
    context = collect_read_only_context(FakeService(), FakeFiscalReserve())

    assert context["system"]["mode"] == "SIMULACAO"
    assert context["system"]["execution_allowed"] is False
    assert context["system"]["real"] == "DESABILITADO"
    assert context["risk"]["allowed"] is False
    assert context["fiscal_reserve"]["total_reserved_brl"] == 0.0
    assert context["recent_decisions"][0]["decision_id"] == "d-1"
    assert context["assistant_safety"]["read_only"] is True
    assert context["assistant_safety"]["may_execute_orders"] is False
    assert context["assistant_safety"]["may_enable_real"] is False
    assert context["assistant_safety"]["may_move_money"] is False


def test_context_rejects_missing_dependencies():
    try:
        collect_read_only_context(None, FakeFiscalReserve())
    except ValueError as exc:
        assert "obrigatórios" in str(exc)
    else:
        raise AssertionError("missing service must be rejected")
