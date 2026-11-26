from core.real_user_authorization import RealUserAuthorizationStore


def test_real_authorization_defaults_disabled(tmp_path):
    store = RealUserAuthorizationStore(tmp_path / "state.sqlite")
    value = store.load()
    assert value.enabled is False
    assert value.authorization_id == "real-disabled"


def test_real_authorization_persists_ecosystem_activation(tmp_path):
    store = RealUserAuthorizationStore(tmp_path / "state.sqlite")
    value = store.enable()
    assert value.enabled is True
    assert store.load().authorization_id == value.authorization_id
    assert store.load().audit_id == value.audit_id


def test_real_deauthorization_is_durable(tmp_path):
    store = RealUserAuthorizationStore(tmp_path / "state.sqlite")
    store.enable()
    value = store.disable()
    assert value.enabled is False
    assert store.load().enabled is False
