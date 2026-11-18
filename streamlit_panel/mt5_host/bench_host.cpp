#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <windowsx.h>
#include <dcomp.h>
#include <WebView2.h>
#include "native_input_router.h"
#include <wrl.h>
#include <wrl/event.h>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cwchar>
#include <fstream>
#include <iterator>
#include <regex>
#include <string>

#pragma comment(lib, "dcomp.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "gdi32.lib")

using Microsoft::WRL::Callback;
using Microsoft::WRL::ComPtr;

namespace {
constexpr wchar_t kClassName[] = L"ControladorTradingBenchHost";
constexpr wchar_t kWindowTitle[] = L"Controlador Trading - Host de bancada";
constexpr wchar_t kStreamlitUrl[] = L"http://127.0.0.1:8501";
constexpr int kToggleSize = 64;
constexpr UINT_PTR kNavigationRetryTimer = 8501;
constexpr UINT_PTR kWebViewRecoveryTimer = 8502;
constexpr UINT kLayoutMessage = WM_APP + 41;

struct HostState {
    HWND window{};
    HWND toggle{};
    ComPtr<ICoreWebView2Environment> environment;
    ComPtr<ICoreWebView2CompositionController> composition;
    ComPtr<ICoreWebView2Controller> controller;
    ComPtr<ICoreWebView2> webview;
    ComPtr<IDCompositionDevice> dcomp;
    ComPtr<IDCompositionTarget> target;
    ComPtr<IDCompositionVisual> root;
    ComPtr<IDCompositionRectangleClip> clip;
    EventRegistrationToken messageToken{};
    EventRegistrationToken moveFocusToken{};
    EventRegistrationToken processFailedToken{};
    EventRegistrationToken acceleratorKeyToken{};
    EventRegistrationToken navigationCompletedToken{};
    bool messageHandlerRegistered{};
    bool moveFocusHandlerRegistered{};
    bool processFailedHandlerRegistered{};
    bool acceleratorKeyHandlerRegistered{};
    bool navigationCompletedHandlerRegistered{};
    bool webviewProcessFailed{};
    unsigned recoveryAttempt{};
    bool initializationInProgress{};
    std::uint64_t generation{};
    std::uint64_t lastSequence{};
    bool layoutValid{};
    bool expanded{};
    // Enabled only by a future chart-attached mode. The standalone bench keeps its title bar.
    bool restrictWindowRegion{};
    RECT shell{};
    controlador::host::PhysicalLayout physicalLayout{};
    controlador::host::MouseCaptureState mouseCapture{};
};

HostState g;

bool ApplyInteractiveWindowRegion(bool includeShell) {
    if (!g.restrictWindowRegion) return true;

    // In chart-attached mode, any inability to constrain the HWND must fail closed.
    // A transparent full-chart host can still intercept input from the MT5 process.
    const auto failClosed = []() {
        if (g.window && IsWindow(g.window)) ShowWindow(g.window, SW_HIDE);
        return false;
    };
    if (!g.window || !g.toggle) return failClosed();

    RECT toggleScreen{}, windowScreen{};
    if (!GetWindowRect(g.toggle, &toggleScreen) ||
        !GetWindowRect(g.window, &windowScreen)) return failClosed();
    POINT origin{0, 0};
    if (!ClientToScreen(g.window, &origin)) return failClosed();

    const RECT toggleWindow{
        toggleScreen.left - windowScreen.left,
        toggleScreen.top - windowScreen.top,
        toggleScreen.right - windowScreen.left,
        toggleScreen.bottom - windowScreen.top
    };
    RECT shellWindow{};
    if (includeShell && g.layoutValid && g.expanded) {
        shellWindow = {
            g.shell.left + origin.x - windowScreen.left,
            g.shell.top + origin.y - windowScreen.top,
            g.shell.right + origin.x - windowScreen.left,
            g.shell.bottom + origin.y - windowScreen.top
        };
    }

    HRGN region = CreateRectRgn(toggleWindow.left, toggleWindow.top,
        toggleWindow.right, toggleWindow.bottom);
    if (!region) return failClosed();
    if (includeShell && g.layoutValid && g.expanded) {
        HRGN shell = CreateRectRgn(shellWindow.left, shellWindow.top,
            shellWindow.right, shellWindow.bottom);
        if (!shell) { DeleteObject(region); return failClosed(); }
        const int combined = CombineRgn(region, region, shell, RGN_OR);
        DeleteObject(shell);
        if (combined == ERROR) { DeleteObject(region); return failClosed(); }
    }

    // SetWindowRgn transfers ownership of the HRGN to Windows on success.
    if (!SetWindowRgn(g.window, region, TRUE)) {
        DeleteObject(region);
        return failClosed();
    }
    // Restore the host only after the safe C-only or C+shell region is installed.
    if (!IsWindowVisible(g.window)) ShowWindow(g.window, SW_SHOWNOACTIVATE);
    return true;
}

bool ReadNumber(const std::string& json, const char* key, double& value) {
    const std::regex pattern(std::string("\"") + key + R"("\s*:\s*(-?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?))");
    std::smatch match;
    if (!std::regex_search(json, match, pattern)) return false;
    try { value = std::stod(match[1].str()); return std::isfinite(value); }
    catch (...) { return false; }
}

bool ReadBool(const std::string& json, const char* key, bool& value) {
    const std::regex pattern(std::string("\"") + key + R"("\s*:\s*(true|false))");
    std::smatch match;
    if (!std::regex_search(json, match, pattern)) return false;
    value = match[1].str() == "true";
    return true;
}

HRESULT CancelMouseCaptureSafely(bool scheduleRecovery = true);

void HideWebView(bool allowRecovery = true) {
    // Preserve failed button releases and recreate WebView2 before accepting
    // more input; recovery teardown itself must not schedule another retry.
    CancelMouseCaptureSafely(allowRecovery);
    g.layoutValid = false;
    g.expanded = false;
    g.physicalLayout = {};
    if (g.controller) g.controller->put_IsVisible(FALSE);
    ApplyInteractiveWindowRegion(false);
}

void ScheduleWebViewRecovery(HRESULT reason) {
    ++g.generation; // Invalidate outstanding callbacks even when retries are exhausted.
    g.initializationInProgress = false;
    if (!g.window || !IsWindow(g.window) || g.recoveryAttempt >= 6) {
        OutputDebugStringW(L"Controlador WebView2 recovery stopped: retry limit reached or host unavailable.\\n");
        return;
    }
    const UINT delay = std::min<UINT>(60000, 5000u << std::min(g.recoveryAttempt, 3u));
    ++g.recoveryAttempt;
    wchar_t message[160]{};
    swprintf_s(message, L"Controlador WebView2 recovery scheduled in %u ms; HRESULT=0x%08X; attempt=%u\\n", delay, static_cast<unsigned>(reason), g.recoveryAttempt);
    OutputDebugStringW(message);
    KillTimer(g.window, kWebViewRecoveryTimer);
    if (!SetTimer(g.window, kWebViewRecoveryTimer, delay, nullptr)) OutputDebugStringW(L"Controlador WebView2 recovery timer could not be created.\\n");
}

HRESULT CancelMouseCaptureSafely(bool scheduleRecovery) {
    const HRESULT result = controlador::host::CancelMouseCapture(
        g.window, g.composition.Get(), g.mouseCapture);
    if (FAILED(result) && scheduleRecovery) ScheduleWebViewRecovery(result);
    return result;
}

void RemoveWebViewEventHandlers() {
    if (g.controller && g.moveFocusHandlerRegistered) {
        g.controller->remove_MoveFocusRequested(g.moveFocusToken);
    }
    g.moveFocusHandlerRegistered = false;
    g.moveFocusToken = {};
    if (g.controller && g.acceleratorKeyHandlerRegistered) {
        g.controller->remove_AcceleratorKeyPressed(g.acceleratorKeyToken);
    }
    g.acceleratorKeyHandlerRegistered = false;
    g.acceleratorKeyToken = {};
    if (g.webview && g.messageHandlerRegistered) {
        g.webview->remove_WebMessageReceived(g.messageToken);
    }
    g.messageHandlerRegistered = false;
    g.messageToken = {};
    if (g.webview && g.navigationCompletedHandlerRegistered) {
        g.webview->remove_NavigationCompleted(g.navigationCompletedToken);
    }
    g.navigationCompletedHandlerRegistered = false;
    g.navigationCompletedToken = {};
    if (g.webview && g.processFailedHandlerRegistered) {
        g.webview->remove_ProcessFailed(g.processFailedToken);
    }
    g.processFailedHandlerRegistered = false;
    g.processFailedToken = {};
}

void ApplyLayout(const std::string& json) {
    double sequence{}, vw{}, vh{}, dpr{}, x{}, y{}, width{}, height{};
    bool expanded{};
    if (!ReadNumber(json, "sequence", sequence) ||
        !ReadNumber(json, "viewportWidth", vw) ||
        !ReadNumber(json, "viewportHeight", vh) ||
        !ReadNumber(json, "devicePixelRatio", dpr) ||
        !ReadBool(json, "expanded", expanded) ||
        sequence <= static_cast<double>(g.lastSequence) ||
        dpr < 0.5 || dpr > 8.0 || vw <= 0 || vh <= 0) {
        HideWebView();
        return;
    }

    RECT client{};
    GetClientRect(g.window, &client);
    const double hostCssWidth = (client.right - client.left) / dpr;
    const double hostCssHeight = (client.bottom - client.top) / dpr;
    if (std::abs(vw - hostCssWidth) > 2.0 || std::abs(vh - hostCssHeight) > 2.0) {
        HideWebView();
        return;
    }

    g.lastSequence = static_cast<std::uint64_t>(sequence);
    if (!expanded) {
        g.layoutValid = true;
        g.expanded = false;
        g.physicalLayout.accepted = true;
        g.physicalLayout.sequence = g.lastSequence;
        g.physicalLayout.webViewVisible = false;
        CancelMouseCaptureSafely();
        g.controller->put_IsVisible(FALSE);
        ApplyInteractiveWindowRegion(false);
        return;
    }

    if (!ReadNumber(json, "x", x) || !ReadNumber(json, "y", y) ||
        !ReadNumber(json, "width", width) || !ReadNumber(json, "height", height) ||
        x < 0 || y < 0 || width <= 0 || height <= 0 ||
        x + width > vw + 1 || y + height > vh + 1) {
        HideWebView();
        return;
    }

    const LONG left = static_cast<LONG>(std::llround(x * dpr));
    const LONG top = static_cast<LONG>(std::llround(y * dpr));
    const LONG right = static_cast<LONG>(std::llround((x + width) * dpr));
    const LONG bottom = static_cast<LONG>(std::llround((y + height) * dpr));
    if (right <= left || bottom <= top ||
        right > client.right + 2 || bottom > client.bottom + 2) {
        HideWebView();
        return;
    }

    g.shell = { left, top, right, bottom };
    g.physicalLayout.accepted = true;
    g.physicalLayout.webViewVisible = true;
    g.physicalLayout.sequence = g.lastSequence;
    g.physicalLayout.clip = g.shell;
    g.clip->SetLeft(static_cast<float>(left));
    g.clip->SetTop(static_cast<float>(top));
    g.clip->SetRight(static_cast<float>(right));
    g.clip->SetBottom(static_cast<float>(bottom));
    g.root->SetClip(g.clip.Get());
    g.dcomp->Commit();
    g.layoutValid = true;
    g.expanded = true;
    g.controller->put_IsVisible(TRUE);
    ApplyInteractiveWindowRegion(true);
}

void InitializeWebView() {
    if (g.initializationInProgress || !g.window || !IsWindow(g.window)) return;
    g.initializationInProgress = true;
    g.webviewProcessFailed = false;
    const std::uint64_t generation = ++g.generation;
    const HRESULT environmentCreation = CreateCoreWebView2EnvironmentWithOptions(
        nullptr, nullptr, nullptr,
        Callback<ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler>(
            [generation](HRESULT result, ICoreWebView2Environment* environment) -> HRESULT {
                if (generation != g.generation) return S_OK;
                if (FAILED(result) || !environment) { const HRESULT failure = FAILED(result) ? result : E_POINTER; HideWebView(); ScheduleWebViewRecovery(failure); return failure; }
                g.environment = environment;
                ComPtr<ICoreWebView2Environment3> environment3;
                HRESULT environmentQuery = g.environment.As(&environment3);
                if (FAILED(environmentQuery)) { ScheduleWebViewRecovery(environmentQuery); return environmentQuery; }
                const HRESULT compositionCreation = environment3->CreateCoreWebView2CompositionController(
                    g.window,
                    Callback<ICoreWebView2CreateCoreWebView2CompositionControllerCompletedHandler>(
                        [generation](HRESULT hr, ICoreWebView2CompositionController* composition) -> HRESULT {
                            if (generation != g.generation) return S_OK;
                            if (FAILED(hr) || !composition) { const HRESULT failure = FAILED(hr) ? hr : E_POINTER; HideWebView(); ScheduleWebViewRecovery(failure); return failure; }
                            g.composition = composition;
                            HRESULT query = g.composition.As(&g.controller);
                            if (FAILED(query)) { ScheduleWebViewRecovery(query); return query; }
                            query = g.controller->get_CoreWebView2(&g.webview);
                            if (FAILED(query)) { ScheduleWebViewRecovery(query); return query; }

                            query = DCompositionCreateDevice(nullptr, IID_PPV_ARGS(&g.dcomp));
                            if (FAILED(query)) { ScheduleWebViewRecovery(query); return query; }
                            query = g.dcomp->CreateTargetForHwnd(g.window, TRUE, &g.target);
                            if (FAILED(query)) { ScheduleWebViewRecovery(query); return query; }
                            query = g.dcomp->CreateVisual(&g.root);
                            if (FAILED(query)) { ScheduleWebViewRecovery(query); return query; }
                            query = g.dcomp->CreateRectangleClip(&g.clip);
                            if (FAILED(query)) { ScheduleWebViewRecovery(query); return query; }
                            g.root->SetContent(nullptr);
                            query = g.composition->put_RootVisualTarget(g.root.Get());
                            if (FAILED(query)) { ScheduleWebViewRecovery(query); return query; }
                            query = g.target->SetRoot(g.root.Get());
                            if (FAILED(query)) { ScheduleWebViewRecovery(query); return query; }
                            query = g.dcomp->Commit();
                            if (FAILED(query)) { ScheduleWebViewRecovery(query); return query; }

                            g.controller->put_IsVisible(FALSE);
                            g.initializationInProgress = false;
                            RECT bounds{};
                            GetClientRect(g.window, &bounds);
                            g.controller->put_Bounds(bounds);

                            // Fail closed on renderer/browser crashes or unresponsiveness:
                            // never leave stale WebView pixels or input capture over the host.
                            query = g.webview->add_ProcessFailed(
                                Callback<ICoreWebView2ProcessFailedEventHandler>(
                                    [generation](ICoreWebView2*, ICoreWebView2ProcessFailedEventArgs* args) -> HRESULT {
                                        if (generation != g.generation) return S_OK;
                                        COREWEBVIEW2_PROCESS_FAILED_KIND kind{};
                                        const HRESULT hr = args->get_ProcessFailedKind(&kind);
                                        HideWebView();
                                        g.webviewProcessFailed = true;
                                        KillTimer(g.window, kNavigationRetryTimer);
                                        ScheduleWebViewRecovery(FAILED(hr) ? hr : HRESULT_FROM_WIN32(ERROR_PROCESS_ABORTED));
                                        if (SUCCEEDED(hr)) {
                                            wchar_t message[128]{};
                                            swprintf_s(message, L"Controlador WebView2 ProcessFailed kind=%d\\n",
                                                static_cast<int>(kind));
                                            OutputDebugStringW(message);
                                        } else {
                                            OutputDebugStringW(L"Controlador WebView2 ProcessFailed (kind unavailable)\\n");
                                        }
                                        return S_OK;
                                    }).Get(), &g.processFailedToken);
                            if (FAILED(query)) { RemoveWebViewEventHandlers(); ScheduleWebViewRecovery(query); return query; }
                            g.processFailedHandlerRegistered = true;

                            // Streamlit is supervised separately by the existing Windows
                            // scheduled task. Retry only the loopback navigation while that
                            // service is starting/restarting; never launch a duplicate server.
                            query = g.webview->add_NavigationCompleted(
                                Callback<ICoreWebView2NavigationCompletedEventHandler>(
                                    [generation](ICoreWebView2*, ICoreWebView2NavigationCompletedEventArgs* args) -> HRESULT {
                                        if (generation != g.generation) return S_OK;
                                        BOOL success = FALSE;
                                        COREWEBVIEW2_WEB_ERROR_STATUS error = COREWEBVIEW2_WEB_ERROR_STATUS_UNKNOWN;
                                        HRESULT hr = args->get_IsSuccess(&success);
                                        if (FAILED(hr)) return hr;
                                        if (success) {
                                            KillTimer(g.window, kNavigationRetryTimer);
                                            g.recoveryAttempt = 0;
                                            OutputDebugStringW(L"Controlador Streamlit navigation ready\\n");
                                        } else {
                                            args->get_WebErrorStatus(&error);
                                            HideWebView();
                                            wchar_t message[160]{};
                                            swprintf_s(message, L"Controlador Streamlit navigation failed; WebErrorStatus=%d. Retry in 5s.\\n",
                                                static_cast<int>(error));
                                            OutputDebugStringW(message);
                                            if (!g.webviewProcessFailed)
                                                SetTimer(g.window, kNavigationRetryTimer, 5000, nullptr);
                                        }
                                        return S_OK;
                                    }).Get(), &g.navigationCompletedToken);
                            if (FAILED(query)) { RemoveWebViewEventHandlers(); ScheduleWebViewRecovery(query); return query; }
                            g.navigationCompletedHandlerRegistered = true;

                            // WebView2 receives ordinary keyboard input while focused.
                            // Accelerator keys are surfaced here; leave Handled=false so
                            // WebView2 keeps its documented default keyboard behavior.
                            query = g.controller->add_AcceleratorKeyPressed(
                                Callback<ICoreWebView2AcceleratorKeyPressedEventHandler>(
                                    [generation](ICoreWebView2Controller*, ICoreWebView2AcceleratorKeyPressedEventArgs*) -> HRESULT {
                                        if (generation != g.generation) return S_OK;
                                        return S_OK;
                                    }).Get(), &g.acceleratorKeyToken);
                            if (FAILED(query)) { RemoveWebViewEventHandlers(); ScheduleWebViewRecovery(query); return query; }
                            g.acceleratorKeyHandlerRegistered = true;

                            // When Tab leaves the WebView, return focus to the native C control.
                            // Normal text/navigation keys remain handled by WebView2 while it owns focus.
                            query = g.controller->add_MoveFocusRequested(
                                Callback<ICoreWebView2MoveFocusRequestedEventHandler>(
                                    [generation](ICoreWebView2Controller*, ICoreWebView2MoveFocusRequestedEventArgs* args) -> HRESULT {
                                        if (generation != g.generation) return S_OK;
                                        COREWEBVIEW2_MOVE_FOCUS_REASON reason{};
                                        HRESULT hr = args->get_Reason(&reason);
                                        if (FAILED(hr)) return hr;
                                        if (reason == COREWEBVIEW2_MOVE_FOCUS_REASON_NEXT ||
                                            reason == COREWEBVIEW2_MOVE_FOCUS_REASON_PREVIOUS) {
                                            args->put_Handled(TRUE);
                                            if (g.toggle && IsWindow(g.toggle)) SetFocus(g.toggle);
                                        }
                                        return S_OK;
                                    }).Get(), &g.moveFocusToken);
                            if (FAILED(query)) { RemoveWebViewEventHandlers(); ScheduleWebViewRecovery(query); return query; }
                            g.moveFocusHandlerRegistered = true;

                            query = g.webview->add_WebMessageReceived(
                                Callback<ICoreWebView2WebMessageReceivedEventHandler>(
                                    [generation](ICoreWebView2*, ICoreWebView2WebMessageReceivedEventArgs* args) -> HRESULT {
                                        if (generation != g.generation) return S_OK;
                                        LPWSTR raw{};
                                        HRESULT hr = args->get_WebMessageAsJson(&raw);
                                        if (FAILED(hr) || !raw) {
                                            if (raw) CoTaskMemFree(raw);
                                            return FAILED(hr) ? hr : E_POINTER;
                                        }
                                        const int count = WideCharToMultiByte(CP_UTF8, 0, raw, -1, nullptr, 0, nullptr, nullptr);
                                        if (count <= 0) {
                                            CoTaskMemFree(raw);
                                            return E_FAIL;
                                        }
                                        std::string json(static_cast<std::size_t>(count), '\0');
                                        const int converted = WideCharToMultiByte(
                                            CP_UTF8, 0, raw, -1, json.data(), count, nullptr, nullptr);
                                        CoTaskMemFree(raw);
                                        if (converted != count) return E_FAIL;
                                        json.resize(static_cast<std::size_t>(count - 1));
                                        if (json.find("controlador.panel.layout") != std::string::npos) {
                                            ApplyLayout(json);
                                        }
                                        return S_OK;
                                    }).Get(), &g.messageToken);
                            if (FAILED(query)) {
                                RemoveWebViewEventHandlers();
                                HideWebView();
                                OutputDebugStringW(L"Controlador WebMessageReceived handler registration failed.\\n");
                                ScheduleWebViewRecovery(query);
                                return query;
                            }

                            g.messageHandlerRegistered = true;

                            wchar_t module[MAX_PATH]{};
                            GetModuleFileNameW(nullptr, module, MAX_PATH);
                            std::wstring bridgePath(module);
                            const auto slash = bridgePath.find_last_of(L"\\/");
                            bridgePath.resize(slash == std::wstring::npos ? 0 : slash + 1);
                            bridgePath += L"dom_bridge.js";
                            std::ifstream file(bridgePath, std::ios::binary);
                            if (!file) { RemoveWebViewEventHandlers(); HideWebView(); const HRESULT failure = HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND); ScheduleWebViewRecovery(failure); return failure; }
                            std::string script((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
                            const int chars = MultiByteToWideChar(CP_UTF8, 0, script.c_str(), -1, nullptr, 0);
                            std::wstring wide(chars > 0 ? chars : 1, L'\0');
                            if (chars > 0) MultiByteToWideChar(CP_UTF8, 0, script.c_str(), -1, wide.data(), chars);
                            const HRESULT scriptRegistration = g.webview->AddScriptToExecuteOnDocumentCreated(
                                wide.c_str(),
                                Callback<ICoreWebView2AddScriptToExecuteOnDocumentCreatedCompletedHandler>(
                                    [generation](HRESULT scriptResult, LPCWSTR) -> HRESULT {
                                        if (generation != g.generation) return S_OK;
                                        if (FAILED(scriptResult)) { RemoveWebViewEventHandlers(); HideWebView(); ScheduleWebViewRecovery(scriptResult); return scriptResult; }
                                        const HRESULT navigation = g.webview->Navigate(kStreamlitUrl);
                                        if (FAILED(navigation)) {
                                            HideWebView();
                                            ScheduleWebViewRecovery(navigation);
                                            OutputDebugStringW(L"Controlador initial Streamlit navigation could not be queued; WebView2 recreation scheduled.\\n");
                                        }
                                        return S_OK;
                                    }).Get());
                            if (FAILED(scriptRegistration)) {
                                RemoveWebViewEventHandlers();
                                HideWebView();
                                ScheduleWebViewRecovery(scriptRegistration);
                            }
                            return scriptRegistration;
                        }).Get());
                if (FAILED(compositionCreation)) ScheduleWebViewRecovery(compositionCreation);
                return compositionCreation;
            }).Get());
    if (FAILED(environmentCreation)) ScheduleWebViewRecovery(environmentCreation);
}

LRESULT CALLBACK WindowProc(HWND hwnd, UINT message, WPARAM wParam, LPARAM lParam) {
    switch (message) {
    case WM_CREATE: {
        g.window = hwnd;
        RECT client{};
        GetClientRect(hwnd, &client);
        g.toggle = CreateWindowExW(0, L"BUTTON", L"C", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
            12, std::max(12L, client.bottom - kToggleSize - 12), kToggleSize, kToggleSize,
            hwnd, reinterpret_cast<HMENU>(1001), GetModuleHandleW(nullptr), nullptr);
        InitializeWebView();
        return 0;
    }
    case WM_ERASEBKGND:
        // WS_EX_NOREDIRECTIONBITMAP leaves the client area to DirectComposition.
        // Do not let DefWindowProc fill it with an opaque class brush.
        return 1;
    case WM_COMMAND:
        if (LOWORD(wParam) == 1001 && g.webview) {
            g.webview->PostWebMessageAsJson(L"{\"type\":\"controlador.toggle\"}");
            return 0;
        }
        break;
    case WM_TIMER:
        if (wParam == kWebViewRecoveryTimer) {
            KillTimer(hwnd, kWebViewRecoveryTimer);
            HideWebView(false);
            RemoveWebViewEventHandlers();
            if (g.controller) g.controller->Close();
            controlador::host::ResetMouseCaptureState(g.mouseCapture);
            g.webview.Reset();
            g.controller.Reset();
            g.composition.Reset();
            g.environment.Reset();
            g.clip.Reset();
            g.root.Reset();
            g.target.Reset();
            g.dcomp.Reset();
            g.initializationInProgress = false;
            g.webviewProcessFailed = false;
            OutputDebugStringW(L"Controlador WebView2 recreating environment after failure.\\n");
            InitializeWebView();
            return 0;
        }
        if (wParam == kNavigationRetryTimer) {
            KillTimer(hwnd, kNavigationRetryTimer);
            if (g.webview && !g.webviewProcessFailed) {
                const HRESULT retry = g.webview->Navigate(kStreamlitUrl);
                if (FAILED(retry)) {
                    OutputDebugStringW(L"Controlador Streamlit navigation retry could not be queued.\\n");
                    SetTimer(hwnd, kNavigationRetryTimer, 5000, nullptr);
                }
            }
            return 0;
        }
        break;
    case WM_SIZE: {
        if (g.controller) {
            HideWebView();
            RECT bounds{};
            GetClientRect(hwnd, &bounds);
            g.controller->put_Bounds(bounds);
        }
        if (g.toggle) {
            RECT client{};
            GetClientRect(hwnd, &client);
            SetWindowPos(g.toggle, nullptr, 12, std::max(12L, client.bottom - kToggleSize - 12),
                kToggleSize, kToggleSize, SWP_NOZORDER | SWP_NOACTIVATE);
        }
        ApplyInteractiveWindowRegion(false);
        return 0;
    }
    case WM_DPICHANGED: {
        // Per-monitor DPI changes include a suggested top-level window rectangle.
        // Apply it instead of merely rereading the old client bounds; WM_SIZE
        // then updates the WebView controller and repositions the native C control.
        HideWebView();
        const RECT* suggested = reinterpret_cast<const RECT*>(lParam);
        if (suggested) {
            SetWindowPos(hwnd, nullptr,
                suggested->left, suggested->top,
                suggested->right - suggested->left,
                suggested->bottom - suggested->top,
                SWP_NOZORDER | SWP_NOACTIVATE);
        }
        if (g.controller) {
            RECT bounds{};
            GetClientRect(hwnd, &bounds);
            g.controller->put_Bounds(bounds);
        }
        ApplyInteractiveWindowRegion(false);
        return 0;
    }
    case WM_MOUSEMOVE:
    case WM_MOUSELEAVE:
    case WM_LBUTTONDOWN:
    case WM_LBUTTONUP:
    case WM_RBUTTONDOWN:
    case WM_RBUTTONUP:
    case WM_MBUTTONDOWN:
    case WM_MBUTTONUP:
    case WM_MOUSEWHEEL:
    case WM_MOUSEHWHEEL:
        if (message == WM_LBUTTONDOWN && g.controller && g.layoutValid &&
            controlador::host::IsInsideClip(g.physicalLayout,
                POINT{ GET_X_LPARAM(lParam), GET_Y_LPARAM(lParam) })) {
            SetFocus(hwnd);
        }
        if (g.composition && g.layoutValid && g.expanded) {
            const HRESULT routed = controlador::host::RouteMouseMessage(
                hwnd, g.composition.Get(), g.physicalLayout, message,
                wParam, lParam, g.mouseCapture);
            if (routed == S_OK) return 0;
            if (FAILED(routed)) {
                controlador::host::CancelMouseCapture(
                    hwnd, g.composition.Get(), g.mouseCapture);
            }
        }
        break;
    case WM_SETFOCUS:
        if (g.controller && g.layoutValid && g.expanded) {
            g.controller->MoveFocus(COREWEBVIEW2_MOVE_FOCUS_REASON_PROGRAMMATIC);
        }
        return 0;
    case WM_SETCURSOR:
        if (LOWORD(lParam) == HTCLIENT && g.composition && g.layoutValid && g.expanded) {
            POINT cursor{};
            if (GetCursorPos(&cursor) && ScreenToClient(hwnd, &cursor)) {
                const HRESULT applied = controlador::host::ApplyWebViewCursor(
                    g.composition.Get(), g.physicalLayout, cursor);
                if (applied == S_OK) return TRUE;
            }
        }
        break;
    case WM_CANCELMODE:
        // Send matching BUTTON_UP events before releasing native capture so
        // WebView2's DOM cannot retain a stuck mouse button.
        controlador::host::CancelMouseCapture(
            hwnd, g.composition.Get(), g.mouseCapture);
        return 0;
    case WM_CAPTURECHANGED:
        if (reinterpret_cast<HWND>(lParam) != hwnd) {
            controlador::host::CancelMouseCapture(
                hwnd, g.composition.Get(), g.mouseCapture);
        }
        break;
    case WM_CLOSE:
        DestroyWindow(hwnd);
        return 0;
    case WM_DESTROY:
        // Centralize shutdown here so WM_CLOSE and externally initiated
        // destruction follow the same idempotent cleanup path.
        KillTimer(hwnd, kNavigationRetryTimer);
        KillTimer(hwnd, kWebViewRecoveryTimer);
        ++g.generation; // Invalidate every outstanding asynchronous callback.
        g.initializationInProgress = false;
        HideWebView(false);
        RemoveWebViewEventHandlers();
        if (g.controller) g.controller->Close();
        controlador::host::ResetMouseCaptureState(g.mouseCapture);
        g.webview.Reset();
        g.controller.Reset();
        g.composition.Reset();
        g.environment.Reset();
        g.clip.Reset();
        g.root.Reset();
        g.target.Reset();
        g.dcomp.Reset();
        g.window = nullptr;
        g.toggle = nullptr;
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(hwnd, message, wParam, lParam);
}
}

struct WindowProbeContext {
    std::wofstream* output{};
    HWND terminal{};
};

void WriteWindowProbeLine(std::wofstream& output, HWND hwnd, const wchar_t* kind, int depth) {
    wchar_t className[256]{};
    wchar_t title[512]{};
    RECT rect{};
    DWORD processId{};
    GetClassNameW(hwnd, className, static_cast<int>(std::size(className)));
    GetWindowTextW(hwnd, title, static_cast<int>(std::size(title)));
    GetWindowRect(hwnd, &rect);
    GetWindowThreadProcessId(hwnd, &processId);
    const auto style = GetWindowLongPtrW(hwnd, GWL_STYLE);
    const auto exStyle = GetWindowLongPtrW(hwnd, GWL_EXSTYLE);
    output << std::wstring(static_cast<size_t>(depth) * 2, L' ')
           << kind << L" hwnd=0x" << std::hex << reinterpret_cast<std::uintptr_t>(hwnd)
           << L" pid=" << std::dec << processId
           << L" visible=" << (IsWindowVisible(hwnd) ? 1 : 0)
           << L" rect=(" << rect.left << L"," << rect.top << L"," << rect.right << L"," << rect.bottom << L")"
           << L" style=0x" << std::hex << style << L" ex=0x" << exStyle
           << L" class=[" << className << L"] title=[" << title << L"]\n";
}

BOOL CALLBACK ProbeChildWindow(HWND hwnd, LPARAM parameter) {
    auto* context = reinterpret_cast<WindowProbeContext*>(parameter);
    int depth = 1;
    HWND parent = GetParent(hwnd);
    while (parent && parent != context->terminal && depth < 32) {
        ++depth;
        parent = GetParent(parent);
    }
    WriteWindowProbeLine(*context->output, hwnd, L"CHILD", depth);
    return TRUE;
}

BOOL CALLBACK ProbeTopLevelWindow(HWND hwnd, LPARAM parameter) {
    auto* output = reinterpret_cast<std::wofstream*>(parameter);
    DWORD processId{};
    GetWindowThreadProcessId(hwnd, &processId);
    HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, processId);
    if (!process) return TRUE;

    wchar_t imagePath[1024]{};
    DWORD imagePathLength = static_cast<DWORD>(std::size(imagePath));
    const BOOL queried = QueryFullProcessImageNameW(process, 0, imagePath, &imagePathLength);
    CloseHandle(process);
    if (!queried) return TRUE;

    const wchar_t* executable = wcsrchr(imagePath, L'\\');
    executable = executable ? executable + 1 : imagePath;
    if (_wcsicmp(executable, L"terminal64.exe") != 0 &&
        _wcsicmp(executable, L"terminal.exe") != 0) return TRUE;

    *output << L"\n=== MT5 PROCESS: " << imagePath << L" ===\n";
    WriteWindowProbeLine(*output, hwnd, L"TOP", 0);
    HWND mdi = FindWindowExW(hwnd, nullptr, L"MDIClient", nullptr);
    if (mdi) {
        WriteWindowProbeLine(*output, mdi, L"MDI", 1);
        HWND active = reinterpret_cast<HWND>(SendMessageW(mdi, WM_MDIGETACTIVE, 0, 0));
        if (active) {
            *output << L"ACTIVE MDI CHILD:\n";
            WriteWindowProbeLine(*output, active, L"ACTIVE", 2);
        }
    }
    WindowProbeContext context{ output, hwnd };
    EnumChildWindows(hwnd, ProbeChildWindow, reinterpret_cast<LPARAM>(&context));
    return TRUE;
}

int RunMt5WindowProbe() {
    wchar_t tempPath[MAX_PATH]{};
    const DWORD length = GetTempPathW(static_cast<DWORD>(std::size(tempPath)), tempPath);
    if (length == 0 || length >= std::size(tempPath)) return 10;
    std::wstring reportPath(tempPath);
    reportPath += L"ControladorTrading-MT5-window-tree.txt";
    std::wofstream output(reportPath);
    if (!output.is_open()) return 11;

    output << L"Read-only MetaTrader 5 HWND diagnostic. No windows are changed.\n";
    EnumWindows(ProbeTopLevelWindow, reinterpret_cast<LPARAM>(&output));
    output.flush();
    output.close();
    MessageBoxW(nullptr, (L"Relatorio salvo em:\n" + reportPath).c_str(),
        L"Controlador Trading - diagnostico MT5", MB_OK | MB_ICONINFORMATION);
    return 0;
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, PWSTR commandLine, int show) {
    if (commandLine && std::wcsstr(commandLine, L"--inspect-mt5")) return RunMt5WindowProbe();
    SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
    if (FAILED(CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED))) return 1;

    WNDCLASSEXW wc{ sizeof(wc) };
    wc.lpfnWndProc = WindowProc;
    wc.hInstance = instance;
    wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    // The HWND must not paint an opaque client background behind the DirectComposition tree.
    wc.hbrBackground = nullptr;
    wc.lpszClassName = kClassName;
    if (!RegisterClassExW(&wc)) return 2;

    HWND window = CreateWindowExW(WS_EX_NOREDIRECTIONBITMAP, kClassName, kWindowTitle, WS_OVERLAPPEDWINDOW,
        CW_USEDEFAULT, CW_USEDEFAULT, 1100, 760, nullptr, nullptr, instance, nullptr);
    if (!window) return 3;
    ShowWindow(window, show);
    UpdateWindow(window);

    MSG msg{};
    while (GetMessageW(&msg, nullptr, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }

    CoUninitialize();
    return static_cast<int>(msg.wParam);
}
