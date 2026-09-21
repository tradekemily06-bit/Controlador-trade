from pathlib import Path

import pytest

from core.technical_incident_store import TechnicalIncidentStore


def test_incident_store_rejects_symlinked_state(tmp_path: Path):
    target = tmp_path / "target.json"
    target.write_text('{"status":"HEALTHY","incident_id":null,"reason":null,"changed_at":null}', encoding="utf-8")
    path = tmp_path / "incident.json"
    try:
        path.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink não suportado neste ambiente")
    with pytest.raises(ValueError, match="arquivo regular"):
        TechnicalIncidentStore(path).status()


def test_incident_store_rejects_oversized_state(tmp_path: Path):
    path = tmp_path / "incident.json"
    path.write_bytes(b"x" * (64 * 1024 + 1))
    with pytest.raises(ValueError, match="estado de incidente técnico inválido"):
        TechnicalIncidentStore(path).status()


def test_incident_store_bounds_reason(tmp_path: Path):
    store = TechnicalIncidentStore(tmp_path / "incident.json")
    with pytest.raises(ValueError, match="excede o limite"):
        store.open("incident-1", "x" * 4097)
