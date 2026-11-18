'use strict';

const fs = require('node:fs');
const assert = require('node:assert/strict');

const host = fs.readFileSync('streamlit_panel/mt5_host/bench_host.cpp', 'utf8');

for (const token of [
  'query = g.webview->add_WebMessageReceived(',
  'if (FAILED(query)) {',
  'WebMessageReceived handler registration failed.',
  'add_ProcessFailed',
  'remove_ProcessFailed',
  'g.webviewProcessFailed = true',
  'kWebViewRecoveryTimer',
  'recoveryAttempt >= 6',
  'ScheduleWebViewRecovery(HRESULT reason)',
  'initializationInProgress',
  'generation != g.generation',
  'recreating environment after failure',
  'recovery scheduled in %u ms',
  'HideWebView();',
  'add_NavigationCompleted',
  'remove_NavigationCompleted',
  'messageHandlerRegistered',
  'moveFocusHandlerRegistered',
  'processFailedHandlerRegistered',
  'acceleratorKeyHandlerRegistered',
  'navigationCompletedHandlerRegistered',
  'void RemoveWebViewEventHandlers()',
  'RemoveWebViewEventHandlers();',
  'kNavigationRetryTimer',
  'SetTimer(g.window, kNavigationRetryTimer, 5000, nullptr)',
  'case WM_TIMER:',
  'g.webview->Navigate(kStreamlitUrl)',
  'initial Streamlit navigation could not be queued',
  'add_AcceleratorKeyPressed',
  'remove_AcceleratorKeyPressed',
  'add_MoveFocusRequested',
  'COREWEBVIEW2_MOVE_FOCUS_REASON_NEXT',
  'COREWEBVIEW2_MOVE_FOCUS_REASON_PREVIOUS',
  'http://127.0.0.1:8501',
  'WS_EX_NOREDIRECTIONBITMAP',
  'wc.hbrBackground = nullptr',
  'case WM_ERASEBKGND:',
  '--inspect-mt5',
  'RunMt5WindowProbe()',
  'EnumWindows(ProbeTopLevelWindow',
  'EnumChildWindows(hwnd, ProbeChildWindow',
  'MDIClient',
  'SetWindowRgn(g.window, region, TRUE)',
  'ApplyInteractiveWindowRegion(false)',
  'ApplyInteractiveWindowRegion(true)',
  'bool restrictWindowRegion{}',
  'const auto failClosed = []()',
  'ShowWindow(g.window, SW_HIDE)',
  'if (!IsWindowVisible(g.window)) ShowWindow(g.window, SW_SHOWNOACTIVATE)',
]) {
  assert.ok(host.includes(token), `Missing native host lifecycle contract: ${token}`);
}

// The existing Windows scheduled task owns Streamlit startup/restart.
// The WebView host must not spawn or terminate a second server process.
for (const forbidden of ['CreateProcessW(', 'TerminateProcess(', 'ShellExecuteExW(']) {
  assert.ok(!host.includes(forbidden), `Host must not own Streamlit process lifecycle: ${forbidden}`);
}

console.log('Native host WebView2 failure, navigation retry, keyboard/focus, and supervisor-boundary contract: OK');
