import pytest
from execution.execution_ledger import ExecutionLedger

def test_ledger_does_not_resolve_symlinked_state(tmp_path):
    target=tmp_path/"target.json"; target.write_text("{}")
    state=tmp_path/"ledger.json"; state.symlink_to(target)
    with pytest.raises(OSError): ExecutionLedger(state).reserve("req")

def test_ledger_refuses_stale_temp(tmp_path):
    state=tmp_path/"ledger.json"; (tmp_path/".ledger.json.tmp").write_text("x")
    with pytest.raises(RuntimeError): ExecutionLedger(state).reserve("req")
