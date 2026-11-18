'use strict';

const fs = require('node:fs');
const assert = require('node:assert/strict');

const host = fs.readFileSync('streamlit_panel/mt5_host/bench_host.cpp', 'utf8');
const diagnostic = fs.readFileSync('streamlit_panel/mt5_host/diagnostico_janelas_mt5_readonly.ps1', 'utf8');
for (const token of [
  'GetActiveMdiChild(IntPtr mdiClient, out bool timedOut)',
  'SMTO_ABORTIFHUNG, 1000, out activeChild',
  'timedOut = completed == IntPtr.Zero',
  'ACTIVE_MDI_CHILD: indisponivel (timeout da thread de interface do MT5).',
  'ACTIVE_MDI_CHILD: nenhum filho MDI ativo foi retornado.'
]) {
  assert.ok(diagnostic.includes(token), `Read-only MT5 diagnostic must preserve distinct MDI outcomes: ${token}`);
}
assert.ok(!diagnostic.includes('SetParent('), 'Read-only diagnostic must never reparent MT5 windows');
assert.ok(!diagnostic.includes('SetWindowRgn('), 'Read-only diagnostic must never change window regions');


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
  'const HRESULT environmentCreation = CreateCoreWebView2EnvironmentWithOptions(',
  'if (FAILED(environmentCreation)) ScheduleWebViewRecovery(environmentCreation)',
  'const HRESULT compositionCreation = environment3->CreateCoreWebView2CompositionController(',
  'if (FAILED(compositionCreation)) ScheduleWebViewRecovery(compositionCreation)',
  '++g.generation; // Invalidate outstanding callbacks even when retries are exhausted.',
  'WebMessageReceived handler registration failed.',
  'ScheduleWebViewRecovery(query);',
  'initializationInProgress',
  'generation != g.generation',
  'recreating environment after failure',
  'recovery scheduled in %u ms',
  'g.recoveryAttempt = 0;',
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
  'SendMessageTimeoutW(',
  'SMTO_ABORTIFHUNG | SMTO_BLOCK, 1000, &activeResult)',
  'ACTIVE MDI CHILD: unavailable (MT5 UI thread timeout)',
  'ACTIVE MDI CHILD: no active MDI child returned',
  'SetWindowRgn(g.window, region, TRUE)',
  'ApplyInteractiveWindowRegion(false)',
  'ApplyInteractiveWindowRegion(true)',
  'bool restrictWindowRegion{}',
  'const auto failClosed = []()',
  'ShowWindow(g.window, SW_HIDE)',
  'if (!IsWindowVisible(g.window)) ShowWindow(g.window, SW_SHOWNOACTIVATE)',
  'case WM_CLOSE:\n        DestroyWindow(hwnd);',
  'case WM_DESTROY:',
  'KillTimer(hwnd, kNavigationRetryTimer);',
  'KillTimer(hwnd, kWebViewRecoveryTimer);',
  '++g.generation; // Invalidate every outstanding asynchronous callback.',
  'g.initializationInProgress = false;',
  'g.webview.Reset();',
  'g.controller.Reset();',
  'g.window = nullptr;',
  'g.toggle = nullptr;',
]) {
  assert.ok(host.includes(token), `Missing native host lifecycle contract: ${token}`);
}


// A hung terminal UI thread must not block the read-only MDI probe.
const probeStart = host.indexOf('BOOL CALLBACK ProbeTopLevelWindow');
const probeEnd = host.indexOf('\nint RunMt5WindowProbe()', probeStart);
assert.ok(probeStart >= 0 && probeEnd > probeStart, 'MT5 top-level probe callback must exist');
const probe = host.slice(probeStart, probeEnd);
assert.ok(probe.includes('SendMessageTimeoutW('), 'MDI active-child query must have a bounded wait');
assert.ok(probe.includes('SMTO_ABORTIFHUNG | SMTO_BLOCK, 1000, &activeResult)'), 'MDI query must abort after a 1-second timeout');
assert.ok(!probe.includes('SendMessageW('), 'Do not use an unbounded synchronous message in the MT5 probe');
assert.ok(probe.includes('ACTIVE MDI CHILD: unavailable (MT5 UI thread timeout)'), 'Probe must distinguish a hung MT5 UI thread');
assert.ok(probe.includes('ACTIVE MDI CHILD: no active MDI child returned'), 'Probe must distinguish an empty MDI state from a timeout');

// The existing Windows scheduled task owns Streamlit startup/restart.
// The WebView host must not spawn or terminate a second server process.
for (const forbidden of ['CreateProcessW(', 'TerminateProcess(', 'ShellExecuteExW(']) {
  assert.ok(!host.includes(forbidden), `Host must not own Streamlit process lifecycle: ${forbidden}`);
}
// Chart attachment is intentionally gated until a real MT5 chart HWND is
// identified and its coordinate/input contract is validated on the target PC.
// Keep the current bench host standalone rather than guessing a parent HWND.
assert.ok(host.includes('bool restrictWindowRegion{}'), 'Interactive window-region restriction must remain disabled in standalone bench mode');
assert.ok(host.includes('CreateWindowExW(WS_EX_NOREDIRECTIONBITMAP, kClassName, kWindowTitle, WS_OVERLAPPEDWINDOW,'), 'Bench host must remain an independent top-level window until chart attachment is validated');
assert.ok(host.includes('CW_USEDEFAULT, CW_USEDEFAULT, 1100, 760, nullptr, nullptr, instance, nullptr)'), 'Bench host must not acquire an unverified parent HWND');
assert.ok(!host.includes('SetParent('), 'Do not attach the host to an unverified MT5 HWND');

console.log('Native host WebView2 failure, navigation retry, keyboard/focus, and supervisor-boundary contract: OK');
