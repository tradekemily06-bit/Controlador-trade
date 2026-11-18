'use strict';

const fs = require('node:fs');
const assert = require('node:assert/strict');

const host = fs.readFileSync('streamlit_panel/mt5_host/bench_host.cpp', 'utf8');

for (const token of [
  'add_ProcessFailed',
  'remove_ProcessFailed',
  'g.webviewProcessFailed = true',
  'HideWebView();',
  'add_NavigationCompleted',
  'remove_NavigationCompleted',
  'kNavigationRetryTimer',
  'SetTimer(g.window, kNavigationRetryTimer, 5000, nullptr)',
  'case WM_TIMER:',
  'g.webview->Navigate(kStreamlitUrl)',
  'add_AcceleratorKeyPressed',
  'remove_AcceleratorKeyPressed',
  'add_MoveFocusRequested',
  'COREWEBVIEW2_MOVE_FOCUS_REASON_NEXT',
  'COREWEBVIEW2_MOVE_FOCUS_REASON_PREVIOUS',
  'http://127.0.0.1:8501',
]) {
  assert.ok(host.includes(token), `Missing native host lifecycle contract: ${token}`);
}

// The existing Windows scheduled task owns Streamlit startup/restart.
// The WebView host must not spawn or terminate a second server process.
for (const forbidden of ['CreateProcessW(', 'TerminateProcess(', 'ShellExecuteExW(']) {
  assert.ok(!host.includes(forbidden), `Host must not own Streamlit process lifecycle: ${forbidden}`);
}

console.log('Native host WebView2 failure, navigation retry, keyboard/focus, and supervisor-boundary contract: OK');
