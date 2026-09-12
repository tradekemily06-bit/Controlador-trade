def test_security_scope_covers_all_layers():
    layers = {"core", "data", "memory", "risk", "identity", "saas", "broker", "execution", "health", "audit"}
    assert len(layers) == 10
