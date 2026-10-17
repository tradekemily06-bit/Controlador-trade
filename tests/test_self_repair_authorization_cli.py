import json

from deployment.authorize_self_repair import main


def _args(**overrides):
    values = {
        "--action": "clear_stale_local_cache",
        "--attempts-used": "0",
        "--max-attempts": "6",
        "--local-only": "true",
        "--reversible": "true",
        "--deterministic": "true",
        "--prevalidated": "true",
        "--external-side-effects": "false",
        "--touches-execution-state": "false",
        "--requires-human-supervision": "false",
        "--cooldown-elapsed": "true",
        "--maintenance-lock-clear": "true",
        "--execution-quiescent": "true",
    }
    values.update(overrides)
    return [part for pair in values.items() for part in pair]


def test_self_repair_cli_allows_explicit_safe_bounded_request(capsys):
    assert main(_args()) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["allowed"] is True
    assert payload["decision"] == "ALLOW_BOUNDED_REPAIR"


def test_self_repair_cli_blocks_external_or_exhausted_repair(capsys):
    assert main(_args(**{"--external-side-effects": "true"})) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["allowed"] is False
    assert payload["decision"] == "ALERT_AND_BLOCK"

    assert main(_args(**{"--attempts-used": "6"})) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["allowed"] is False


def test_self_repair_cli_allows_controller_restart_only_with_quiescence(capsys, monkeypatch):
    monkeypatch.setenv('CONTROLADOR_EXECUTION_PROVIDER', 'ic_markets_mt5_demo')
    for name in ('CONTROLADOR_REAL_EXPLICITLY_ENABLED', 'CONTROLADOR_REAL_EXECUTION_ALLOWED', 'CONTROLADOR_REAL_AUDIT_VERIFIED', 'CONTROLADOR_REAL_RISK_APPROVED'):
        monkeypatch.setenv(name, 'false')
    assert main(_args(**{"--action": "restart_controller"})) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["allowed"] is True

    assert main(_args(**{"--action": "restart_controller", "--execution-quiescent": "false"})) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["allowed"] is False
    assert "posições/ordens abertas" in payload["reason"]


def test_self_repair_cli_allows_terminal_start_without_restart_quiescence(capsys, monkeypatch):
    monkeypatch.setenv('CONTROLADOR_EXECUTION_PROVIDER', 'ic_markets_mt5_demo')
    for name in ('CONTROLADOR_REAL_EXPLICITLY_ENABLED', 'CONTROLADOR_REAL_EXECUTION_ALLOWED', 'CONTROLADOR_REAL_AUDIT_VERIFIED', 'CONTROLADOR_REAL_RISK_APPROVED'):
        monkeypatch.setenv(name, 'false')
    assert main(_args(**{"--action": "start_mt5_terminal", "--execution-quiescent": "false"})) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["allowed"] is True


def test_self_repair_cli_blocks_process_actions_without_demo_only_environment(capsys, monkeypatch):
    monkeypatch.delenv("CONTROLADOR_EXECUTION_PROVIDER", raising=False)
    for name in ("CONTROLADOR_REAL_EXPLICITLY_ENABLED", "CONTROLADOR_REAL_EXECUTION_ALLOWED", "CONTROLADOR_REAL_AUDIT_VERIFIED", "CONTROLADOR_REAL_RISK_APPROVED"):
        monkeypatch.delenv(name, raising=False)
    assert main(_args(**{"--action": "start_mt5_terminal"})) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["allowed"] is False
    assert "provider DEMO" in payload["reason"]

    monkeypatch.setenv("CONTROLADOR_EXECUTION_PROVIDER", "ic_markets_mt5_demo")
    monkeypatch.setenv("CONTROLADOR_REAL_EXECUTION_ALLOWED", "true")
    assert main(_args(**{"--action": "start_mt5_terminal"})) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["allowed"] is False
    assert "bloqueio REAL" in payload["reason"]
