from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deployment" / "sync_mql5_panel.ps1"


def test_mql5_sync_script_exists_and_is_self_contained():
    text = SCRIPT.read_text(encoding="utf-8")
    for required in (
        "terminal_info()",
        "data_path",
        "ControladorTradingPanel.mq5",
        "metaeditor64.exe",
        "/compile:",
        "errors",
        "warnings",
        "backup",
    ):
        assert required in text


def test_mql5_panel_has_single_repository_source():
    panel = ROOT / "mql5" / "Experts" / "ControladorTrading" / "ControladorTradingPanel.mq5"
    assert panel.is_file()
