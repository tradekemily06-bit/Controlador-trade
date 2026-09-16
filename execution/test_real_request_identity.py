from core.models import Signal
from execution.ports import ExecutionMode, ExecutionRequest
from execution.real_gateway import RealExecutionGateway


def test_real_request_requires_identity_bound_request_id():
    request = ExecutionRequest("TEST", Signal.COMPRA, 1.0, 60, ExecutionMode.REAL)
    assert RealExecutionGateway._valid_request(request) is False


def test_real_request_identity_must_be_non_blank():
    request = ExecutionRequest("TEST", Signal.COMPRA, 1.0, 60, ExecutionMode.REAL, "   ")
    assert RealExecutionGateway._valid_request(request) is False
