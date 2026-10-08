from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_runtime_launchers_resolve_python_and_fail_closed():
    for name in (
        "deployment/start_controlador_runtime.ps1",
        "deployment/start_mt5_runtime.ps1",
        "deployment/bootstrap_windows_runtime.ps1",
        "deployment/backup_runtime.ps1",
        "deployment/restore_runtime.ps1",
    ):
        text = _read(name)
        assert "Get-Command $PythonExe" in text
        assert "Python não encontrado" in text
        assert "Test-Path -LiteralPath $PythonExe -PathType Leaf" in text


def test_bootstrap_stops_after_dependency_install_failure():
    text = _read("deployment/bootstrap_windows_runtime.ps1")
    assert "$LASTEXITCODE -ne 0" in text
    assert "Falha ao instalar requirements.txt." in text
    assert "Falha ao instalar requirements-mt5.txt." in text
    assert "MetaTrader5 não pôde ser importado" in text
