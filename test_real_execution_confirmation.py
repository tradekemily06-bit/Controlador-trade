from core.real_execution_confirmation import (
    ExecutionConfirmation,
    RealExecutionRequest,
    new_real_confirmation,
)


def test_real_confirmation_requires_exact_phrase():
    confirmation = new_real_confirmation(
        confirmation_id="c-1",
        request_id="r-1",
        phrase="CONFIRMO REAL",
    )
    request = RealExecutionRequest(
        request_id="r-1",
        symbol="EURUSD",
        signal=__import__("core.models", fromlist=["Signal"]).Signal.COMPRA,
        amount=0.01,
        duration_seconds=60,
        confirmation=confirmation,
    )
    assert request.as_execution_request().mode.value == "REAL"


def test_real_confirmation_rejects_wrong_phrase():
    try:
        new_real_confirmation(
            confirmation_id="c-1",
            request_id="r-1",
            phrase="SIM",
        )
    except ValueError:
        return
    raise AssertionError("confirmação REAL deveria exigir frase explícita")


def test_confirmation_cannot_be_reused_for_another_request():
    confirmation = new_real_confirmation(
        confirmation_id="c-1",
        request_id="r-1",
        phrase="CONFIRMO REAL",
    )
    try:
        RealExecutionRequest(
            request_id="r-2",
            symbol="EURUSD",
            signal=__import__("core.models", fromlist=["Signal"]).Signal.COMPRA,
            amount=0.01,
            duration_seconds=60,
            confirmation=confirmation,
        )
    except ValueError:
        return
    raise AssertionError("confirmation de outro request_id não deveria ser aceita")
