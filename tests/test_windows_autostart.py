from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_windows_launcher_uses_trusted_python_and_shared_app_runtime():
    script = (ROOT / "scripts" / "start_controlador.ps1").read_text(encoding="utf-8")
    assert "trustedRoots" in script
    assert "from app import run" in script
    assert "host='127.0.0.1'" in script


def test_windows_launcher_does_not_start_duplicate_runtime():
    start = (ROOT / "scripts" / "start_controlador.ps1").read_text(encoding="utf-8")
    stop = (ROOT / "scripts" / "stop_controlador.ps1").read_text(encoding="utf-8")
    for script in (start, stop):
        assert 'from app import run' in script
        assert '*$Root*app.py*' in script


def test_autostart_uses_least_privilege_login_task():
    script = (ROOT / "scripts" / "install_autostart.ps1").read_text(encoding="utf-8")
    assert "AtLogOn" in script
    assert "LeastPrivilege" in script
    assert "RunLevel" in script
