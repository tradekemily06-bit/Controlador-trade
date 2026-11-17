"""Preview-only React host attached to the MT5 window.

This does not modify the EA, send orders, or connect trading actions.
It displays the local Vite React preview in a clipped WebView2 overlay.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

os.environ["WEBVIEW2_DEFAULT_BACKGROUND_COLOR"] = "00FFFFFF"

import ctypes
import win32con
import win32gui
import webview
import webview.platforms.winforms as wf

BASE = Path(__file__).resolve().parent
URL = "http://127.0.0.1:4173"
VISIBLE_WIDTH = 436
VISIBLE_HEIGHT = 476
STARTUP_TIMEOUT = 90


def find_mt5_window() -> int | None:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-Process terminal64 -ErrorAction SilentlyContinue | "
            "Where-Object {$_.MainWindowHandle -ne 0} | "
            "Select-Object -First 1 -ExpandProperty MainWindowHandle)",
        ],
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    value = result.stdout.strip()
    try:
        return int(value) if value else None
    except ValueError:
        return None


def wait_for_preview() -> None:
    deadline = time.time() + STARTUP_TIMEOUT
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(URL, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            pass
        time.sleep(1)
    raise SystemExit("A prévia React não iniciou em 127.0.0.1:4173.")


def attach_to_mt5(window, mt5_hwnd: int) -> None:
    time.sleep(1)
    handles: list[int] = []

    def collect(hwnd: int, _: object) -> None:
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) == "Control Hub React - MT5":
            handles.append(hwnd)

    win32gui.EnumWindows(collect, None)
    if not handles:
        raise RuntimeError("Janela WebView2 não localizada.")

    hwnd = handles[0]
    native = window.native
    native.BackColor = wf.Color.Magenta
    native.TransparencyKey = wf.Color.Magenta
    native.browser.DefaultBackgroundColor = wf.Color.Transparent
    native.Enabled = True
    native.browser.Enabled = True

    exstyle = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, exstyle | 0x00080000)
    ctypes.windll.user32.SetLayeredWindowAttributes(
        hwnd, 0x00FF00FF, 255, 0x00000001
    )

    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
    style = (style & ~win32con.WS_POPUP) | win32con.WS_CHILD | win32con.WS_VISIBLE
    win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
    win32gui.SetParent(hwnd, mt5_hwnd)

    rect = win32gui.GetClientRect(mt5_hwnd)
    width, height = rect[2], rect[3]
    if width <= 0 or height <= 0:
        raise RuntimeError("Não foi possível medir a área do MT5.")

    win32gui.SetWindowPos(
        hwnd,
        0,
        0,
        0,
        width,
        height,
        win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED | win32con.SWP_SHOWWINDOW,
    )

    visible_width = min(width, VISIBLE_WIDTH)
    visible_height = min(height, VISIBLE_HEIGHT)
    top = height - visible_height
    gdi32 = ctypes.windll.gdi32
    user32 = ctypes.windll.user32
    region = gdi32.CreateRectRgn(0, top, visible_width, height)
    if not region or not user32.SetWindowRgn(hwnd, region, True):
        if region:
            gdi32.DeleteObject(region)
        raise RuntimeError("Não foi possível limitar a área visível do painel.")

    window.evaluate_js("""
      (() => {
        const style = document.createElement("style");
        style.id = "mt5-react-transparent-host";
        style.textContent = "html, body, #root, .chart-surface { background: transparent !important; background-color: transparent !important; background-image: none !important; }";
        document.head.appendChild(style);
        document.documentElement.style.background = "transparent";
        document.body.style.background = "transparent";
      })();
    """)
    print("PRÉVIA REACT anexada ao MT5.")
    print("Somente navegação visual; nenhuma ordem ou ação operacional é executada.")
    print("Para fechar, encerre esta janela do host.")


def main() -> None:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise SystemExit("Node.js/npm não encontrado. Instale Node.js LTS antes de iniciar.")

    if not (BASE / "node_modules").is_dir():
        print("Instalando dependências da prévia React...")
        subprocess.run(["cmd", "/c", npm, "install"], cwd=str(BASE), check=True)

    mt5_hwnd = find_mt5_window()
    if not mt5_hwnd:
        raise SystemExit("Abra o MetaTrader 5 antes de iniciar a prévia.")

    server = subprocess.Popen(
        f'"{npm}" run dev -- --host 127.0.0.1 --port 4173 --strictPort',
        cwd=str(BASE),
        shell=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        wait_for_preview()
        rect = win32gui.GetClientRect(mt5_hwnd)
        width, height = rect[2], rect[3]
        if width <= 0 or height <= 0:
            raise SystemExit("A janela do MT5 não possui área visível.")

        window = webview.create_window(
            "Control Hub React - MT5",
            URL,
            width=width,
            height=height,
            x=0,
            y=0,
            resizable=False,
            frameless=True,
            easy_drag=False,
            on_top=False,
            transparent=True,
        )
        window.events.loaded += lambda: attach_to_mt5(window, mt5_hwnd)
        print("Iniciando prévia React no MT5...")
        webview.start(gui="edgechromium")
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()


if __name__ == "__main__":
    main()
