"""Attach the local Streamlit panel to the MT5 chart as a transparent WebView2 overlay.

Start the Controlador runtime and Streamlit supervisor first. This host only displays
the existing local panel; it does not connect to a broker or submit trading orders.
"""
import ctypes
import os
import subprocess
import threading
import time
import urllib.request

import win32con
import win32gui

os.environ["WEBVIEW2_DEFAULT_BACKGROUND_COLOR"] = "00FFFFFF"

import webview
import webview.platforms.winforms as wf


BASE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(BASE, "app.py")
URL = "http://127.0.0.1:8501"
HEALTH_URL = URL + "/_stcore/health"
VISIBLE_WIDTH = 436
VISIBLE_HEIGHT = 476

REQUIRED_APP_MARKERS = (
    'st.session_state.panel_open = False',
    'st.button("C", key="open_control_hub", help="Abrir painel")',
    'st.button("C", key="close_control_hub", help="Recolher painel")',
    '.st-key-panel-toggle { position: fixed; left: 18px; bottom: 14px;',
    'AREA_SOURCE_NAMES = {',
)

if not os.path.isfile(APP):
    raise SystemExit(f"Aplicação Streamlit não encontrada: {APP}")

with open(APP, "r", encoding="utf-8") as app_file:
    app_source = app_file.read()

missing_markers = [marker for marker in REQUIRED_APP_MARKERS if marker not in app_source]
if missing_markers:
    raise SystemExit(
        "A versão do app.py não corresponde ao contrato do host MT5. "
        "Integração interrompida sem alterar o painel. Marcadores ausentes: "
        + ", ".join(missing_markers)
    )

deadline = time.time() + 180
mt5_handle = None
streamlit_ready = False

while time.time() < deadline:
    if mt5_handle is None:
        check = subprocess.run(
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
            check=False,
        )
        value = check.stdout.strip()
        if value:
            try:
                mt5_handle = int(value)
            except ValueError:
                mt5_handle = None

    if not streamlit_ready:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=2) as response:
                body = response.read().decode("utf-8", errors="replace").strip()
                streamlit_ready = response.status == 200 and body == "ok"
        except Exception:
            streamlit_ready = False

    if mt5_handle is not None and streamlit_ready:
        break
    time.sleep(2)

if mt5_handle is None:
    raise SystemExit("MT5 não encontrado. Abra o MetaTrader 5.")
if not streamlit_ready:
    raise SystemExit("Streamlit não respondeu em 127.0.0.1:8501/_stcore/health.")

mt5_rect = win32gui.GetClientRect(mt5_handle)
width, height = mt5_rect[2], mt5_rect[3]
if width <= 0 or height <= 0:
    raise SystemExit("Não foi possível medir a área do MT5.")

window = webview.create_window(
    "Controlador Trading - MT5",
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


def attach_to_mt5():
    time.sleep(1)
    handles = []

    def find_host(hwnd, _):
        if (
            win32gui.IsWindowVisible(hwnd)
            and win32gui.GetWindowText(hwnd) == "Controlador Trading - MT5"
        ):
            handles.append(hwnd)

    win32gui.EnumWindows(find_host, None)
    if not handles:
        print("Janela WebView2 não localizada; painel não foi alterado.", flush=True)
        return

    hwnd = handles[0]
    native = window.native
    native.BackColor = wf.Color.Magenta
    native.TransparencyKey = wf.Color.Magenta
    native.browser.DefaultBackgroundColor = wf.Color.Transparent
    native.Enabled = True
    native.browser.Enabled = True

    exstyle = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, exstyle | 0x00080000)
    transparent_ok = ctypes.windll.user32.SetLayeredWindowAttributes(
        hwnd, 0x00FF00FF, 255, 0x00000001
    )
    print("TRANSPARÊNCIA NATIVA:", bool(transparent_ok), flush=True)

    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
    style = (style & ~win32con.WS_POPUP) | win32con.WS_CHILD | win32con.WS_VISIBLE
    win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
    win32gui.SetParent(hwnd, mt5_handle)
    win32gui.SetWindowPos(
        hwnd,
        0,
        0,
        0,
        width,
        height,
        win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED | win32con.SWP_SHOWWINDOW,
    )

    # Preserve the existing 436x476 MT5 chart area. The C remains at 18px/14px;
    # the panel sits above it with a 14px gap, so the two surfaces do not overlap.
    visible_width = min(width, VISIBLE_WIDTH)
    visible_height = min(height, VISIBLE_HEIGHT)
    top = height - visible_height
    gdi32 = ctypes.windll.gdi32
    user32 = ctypes.windll.user32
    region = gdi32.CreateRectRgn(0, top, visible_width, height)
    if not region:
        print("Aviso: não foi possível criar o recorte visual.", flush=True)
    elif not user32.SetWindowRgn(hwnd, region, True):
        gdi32.DeleteObject(region)
        print("Aviso: recorte visual não aplicado.", flush=True)

    try:
        window.evaluate_js(
            """
            (() => {
              const css = `
.st-key-panel-toggle {
  position: fixed !important;
  left: 18px !important;
  bottom: 14px !important;
  z-index: 1000 !important;
}
.st-key-control-hub-shell {
  position: fixed !important;
  left: 12px !important;
  bottom: 76px !important;
  width: min(calc(100vw - 24px), 412px) !important;
  max-width: 412px !important;
  max-height: 400px !important;
  overflow-y: auto !important;
  margin: 0 !important;
}
html, body, #root, .stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stMainBlockContainer"],
[data-testid="stHeader"],
[data-testid="stToolbar"],
section.main, .block-container {
  background: transparent !important;
  background-color: transparent !important;
  background-image: none !important;
  box-shadow: none !important;
}
`;
              let style = document.getElementById("mt5-transparent-host");
              if (!style) {
                style = document.createElement("style");
                style.id = "mt5-transparent-host";
                document.head.appendChild(style);
              }
              style.textContent = css;
              document.documentElement.style.background = "transparent";
              document.body.style.background = "transparent";
            })();
            """
        )
        print("CSS do host aplicado; C e painel mantêm posições separadas.", flush=True)
    except Exception as exc:
        print("Aviso: transparência/posicionamento não confirmados:", repr(exc), flush=True)

    try:
        native_control = native.browser.webview
        control_handle = int(native_control.Handle.ToInt64())
        parent = native_control.Parent
        parent_handle = int(parent.Handle.ToInt64()) if parent is not None else 0
        print(
            "DIAG WEBVIEW:",
            {
                "host_hwnd": int(native.Handle.ToInt64()),
                "host_parent": win32gui.GetParent(hwnd),
                "control_hwnd": control_handle,
                "control_parent_dotnet": parent_handle,
                "control_parent_win32": win32gui.GetParent(control_handle),
                "enabled": bool(native_control.Enabled),
                "visible": bool(native_control.Visible),
                "bounds": str(native_control.Bounds),
            },
            flush=True,
        )
    except Exception as exc:
        print("DIAG NATIVO WEBVIEW:", repr(exc), flush=True)

    try:
        details = window.evaluate_js(
            """
            (() => {
              window.__mt5LastPointerEvent = "";
              if (!window.__mt5ClickTraceInstalled) {
                window.__mt5ClickTraceInstalled = true;
                const capture = (kind, event) => {
                  const target = event.target;
                  const button = target && target.closest ? target.closest("button") : null;
                  window.__mt5LastPointerEvent = JSON.stringify({
                    event: kind,
                    target: target?.tagName || null,
                    targetClass: target ? String(target.className) : null,
                    targetText: target ? (target.innerText || target.textContent || "").trim().slice(0, 80) : "",
                    buttonText: button ? (button.innerText || button.textContent || "").trim() : null,
                    disabled: button ? button.disabled : null,
                    x: event.clientX,
                    y: event.clientY,
                    time: Date.now()
                  });
                };
                document.addEventListener("pointerdown", event => capture("pointerdown", event), true);
                document.addEventListener("click", event => capture("click", event), true);
              }
              const buttons = [...document.querySelectorAll("button")];
              const button = buttons.find(item => (item.innerText || item.textContent || "").trim() === "C");
              if (!button) {
                return JSON.stringify({
                  url: location.href,
                  readyState: document.readyState,
                  buttons: buttons.map(item => (item.innerText || item.textContent || "").trim()).slice(0, 30),
                  panelToggle: null
                });
              }
              const rect = button.getBoundingClientRect();
              const style = getComputedStyle(button);
              const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
              return JSON.stringify({
                url: location.href,
                readyState: document.readyState,
                panelToggle: {
                  disabled: button.disabled,
                  rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
                  pointerEvents: style.pointerEvents,
                  visibility: style.visibility,
                  display: style.display,
                  zIndex: style.zIndex,
                  hitTag: hit?.tagName || null,
                  hitText: (hit?.innerText || hit?.textContent || "").trim().slice(0, 80)
                }
              });
            })();
            """
        )
        print("DIAGNÓSTICO DOM DO C:", details, flush=True)
    except Exception as exc:
        print("ERRO NO DIAGNÓSTICO DOM:", repr(exc), flush=True)

    def watch_dom_events():
        previous = ""
        while True:
            try:
                current = window.evaluate_js("window.__mt5LastPointerEvent || ''")
                if current and current != previous:
                    print("EVENTO DOM CAPTURADO:", current, flush=True)
                    previous = current
            except Exception:
                pass
            time.sleep(0.25)

    threading.Thread(target=watch_dom_events, daemon=True).start()
    print("MONITOR DOM ATIVO: clique uma vez no C dentro do MT5.", flush=True)
    print("Host conectado ao Streamlit local em 127.0.0.1:8501.", flush=True)


window.events.loaded += attach_to_mt5
print("Abrindo host de diagnóstico do painel MT5...", flush=True)
webview.start(gui="edgechromium")
