from core.operation_memory_store import OperationMemoryStore

def test_memory_rejects_symlink_target_and_stale_temp(tmp_path):
    target=tmp_path/"target.json"; target.write_text("[]")
    state=tmp_path/"memory.json"; state.symlink_to(target)
    store=OperationMemoryStore(state)
    import pytest
    with pytest.raises(OSError): store.save(__import__("core.operation_memory",fromlist=["OperationMemory"]).OperationMemory())

def test_memory_refuses_stale_temp(tmp_path):
    from core.operation_memory import OperationMemory
    import pytest
    state=tmp_path/"memory.json"; (tmp_path/".memory.json.tmp").write_text("x")
    with pytest.raises(RuntimeError): OperationMemoryStore(state).save(OperationMemory())
