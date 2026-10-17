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
