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
#include <fstream>
#include <iterator>
#include <regex>
#include <string>

#pragma comment(lib, "dcomp.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "user32.lib")

using Microsoft::WRL::Callback;
using Microsoft::WRL::ComPtr;

namespace {
constexpr wchar_t kClassName[] = L"ControladorTradingBenchHost";
constexpr wchar_t kWindowTitle[] = L"Controlador Trading - Host de bancada";
constexpr wchar_t kStreamlitUrl[] = L"http://127.0.0.1:8501";
constexpr int kToggleSize = 64;
constexpr UINT_PTR kNavigationRetryTimer = 8501;
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
    bool webviewProcessFailed{};
    std::uint64_t lastSequence{};
    bool layoutValid{};
    bool expanded{};
    RECT shell{};
    controlador::host::PhysicalLayout physicalLayout{};
    controlador::host::MouseCaptureState mouseCapture{};
};

HostState g;

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

void HideWebView() {
    g.layoutValid = false;
    g.expanded = false;
    g.physicalLayout = {};
    g.mouseCapture = {};
    if (GetCapture() == g.window) ReleaseCapture();
    if (g.controller) g.controller->put_IsVisible(FALSE);
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
        g.mouseCapture = {};
        g.controller->put_IsVisible(FALSE);
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
}

void InitializeWebView() {
    CreateCoreWebView2EnvironmentWithOptions(
        nullptr, nullptr, nullptr,
        Callback<ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler>(
            [](HRESULT result, ICoreWebView2Environment* environment) -> HRESULT {
                if (FAILED(result) || !environment) { HideWebView(); return result; }
                g.environment = environment;
                ComPtr<ICoreWebView2Environment3> environment3;
                HRESULT environmentQuery = g.environment.As(&environment3);
                if (FAILED(environmentQuery)) return environmentQuery;
                return environment3->CreateCoreWebView2CompositionController(
                    g.window,
                    Callback<ICoreWebView2CreateCoreWebView2CompositionControllerCompletedHandler>(
                        [](HRESULT hr, ICoreWebView2CompositionController* composition) -> HRESULT {
                            if (FAILED(hr) || !composition) { HideWebView(); return hr; }
                            g.composition = composition;
                            HRESULT query = g.composition.As(&g.controller);
                            if (FAILED(query)) return query;
                            query = g.controller->get_CoreWebView2(&g.webview);
                            if (FAILED(query)) return query;

                            query = DCompositionCreateDevice(nullptr, IID_PPV_ARGS(&g.dcomp));
                            if (FAILED(query)) return query;
                            query = g.dcomp->CreateTargetForHwnd(g.window, TRUE, &g.target);
                            if (FAILED(query)) return query;
                            query = g.dcomp->CreateVisual(&g.root);
                            if (FAILED(query)) return query;
                            query = g.dcomp->CreateRectangleClip(&g.clip);
                            if (FAILED(query)) return query;
                            g.root->SetContent(nullptr);
                            query = g.composition->put_RootVisualTarget(g.root.Get());
                            if (FAILED(query)) return query;
                            query = g.target->SetRoot(g.root.Get());
                            if (FAILED(query)) return query;
                            query = g.dcomp->Commit();
                            if (FAILED(query)) return query;

                            g.controller->put_IsVisible(FALSE);
                            RECT bounds{};
                            GetClientRect(g.window, &bounds);
                            g.controller->put_Bounds(bounds);

                            // Fail closed on renderer/browser crashes or unresponsiveness:
                            // never leave stale WebView pixels or input capture over the host.
                            query = g.webview->add_ProcessFailed(
                                Callback<ICoreWebView2ProcessFailedEventHandler>(
                                    [](ICoreWebView2*, ICoreWebView2ProcessFailedEventArgs* args) -> HRESULT {
                                        COREWEBVIEW2_PROCESS_FAILED_KIND kind{};
                                        const HRESULT hr = args->get_ProcessFailedKind(&kind);
                                        HideWebView();
                                        g.webviewProcessFailed = true;
                                        KillTimer(g.window, kNavigationRetryTimer);
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
                            if (FAILED(query)) return query;

                            // Streamlit is supervised separately by the existing Windows
                            // scheduled task. Retry only the loopback navigation while that
                            // service is starting/restarting; never launch a duplicate server.
                            query = g.webview->add_NavigationCompleted(
                                Callback<ICoreWebView2NavigationCompletedEventHandler>(
                                    [](ICoreWebView2*, ICoreWebView2NavigationCompletedEventArgs* args) -> HRESULT {
                                        BOOL success = FALSE;
                                        COREWEBVIEW2_WEB_ERROR_STATUS error = COREWEBVIEW2_WEB_ERROR_STATUS_UNKNOWN;
                                        HRESULT hr = args->get_IsSuccess(&success);
                                        if (FAILED(hr)) return hr;
                                        if (success) {
                                            KillTimer(g.window, kNavigationRetryTimer);
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
                            if (FAILED(query)) return query;

                            // WebView2 receives ordinary keyboard input while focused.
                            // Accelerator keys are surfaced here; leave Handled=false so
                            // WebView2 keeps its documented default keyboard behavior.
                            query = g.controller->add_AcceleratorKeyPressed(
                                Callback<ICoreWebView2AcceleratorKeyPressedEventHandler>(
                                    [](ICoreWebView2Controller*, ICoreWebView2AcceleratorKeyPressedEventArgs*) -> HRESULT {
                                        return S_OK;
                                    }).Get(), &g.acceleratorKeyToken);
                            if (FAILED(query)) return query;

                            // When Tab leaves the WebView, return focus to the native C control.
                            // Normal text/navigation keys remain handled by WebView2 while it owns focus.
                            query = g.controller->add_MoveFocusRequested(
                                Callback<ICoreWebView2MoveFocusRequestedEventHandler>(
                                    [](ICoreWebView2Controller*, ICoreWebView2MoveFocusRequestedEventArgs* args) -> HRESULT {
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
                            if (FAILED(query)) return query;

                            g.webview->add_WebMessageReceived(
                                Callback<ICoreWebView2WebMessageReceivedEventHandler>(
                                    [](ICoreWebView2*, ICoreWebView2WebMessageReceivedEventArgs* args) -> HRESULT {
                                        LPWSTR raw{};
                                        HRESULT hr = args->get_WebMessageAsJson(&raw);
                                        if (FAILED(hr) || !raw) return hr;
                                        const int count = WideCharToMultiByte(CP_UTF8, 0, raw, -1, nullptr, 0, nullptr, nullptr);
                                        std::string json(count > 0 ? count : 1, '\0');
                                        if (count > 0) WideCharToMultiByte(CP_UTF8, 0, raw, -1, json.data(), count, nullptr, nullptr);
                                        CoTaskMemFree(raw);
                                        if (json.find("controlador.panel.layout") != std::string::npos) {
                                            ApplyLayout(json);
                                        }
                                        return S_OK;
                                    }).Get(), &g.messageToken);

                            wchar_t module[MAX_PATH]{};
                            GetModuleFileNameW(nullptr, module, MAX_PATH);
                            std::wstring bridgePath(module);
                            const auto slash = bridgePath.find_last_of(L"\\/");
                            bridgePath.resize(slash == std::wstring::npos ? 0 : slash + 1);
                            bridgePath += L"dom_bridge.js";
                            std::ifstream file(bridgePath, std::ios::binary);
                            if (!file) { HideWebView(); return HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND); }
                            std::string script((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
                            const int chars = MultiByteToWideChar(CP_UTF8, 0, script.c_str(), -1, nullptr, 0);
                            std::wstring wide(chars > 0 ? chars : 1, L'\0');
                            if (chars > 0) MultiByteToWideChar(CP_UTF8, 0, script.c_str(), -1, wide.data(), chars);
                            return g.webview->AddScriptToExecuteOnDocumentCreated(
                                wide.c_str(),
                                Callback<ICoreWebView2AddScriptToExecuteOnDocumentCreatedCompletedHandler>(
                                    [](HRESULT scriptResult, LPCWSTR) -> HRESULT {
                                        if (FAILED(scriptResult)) { HideWebView(); return scriptResult; }
                                        return g.webview->Navigate(kStreamlitUrl);
                                    }).Get());
                        }).Get());
            }).Get());
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
    case WM_COMMAND:
        if (LOWORD(wParam) == 1001 && g.webview) {
            g.webview->PostWebMessageAsJson(L"{\"type\":\"controlador.toggle\"}");
            return 0;
        }
        break;
    case WM_TIMER:
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
    case WM_CAPTURECHANGED:
        if (reinterpret_cast<HWND>(lParam) != hwnd) g.mouseCapture = {};
        break;
    case WM_CLOSE:
        HideWebView();
        if (g.controller) g.controller->remove_MoveFocusRequested(g.moveFocusToken);
        if (g.webview) {
            g.webview->remove_WebMessageReceived(g.messageToken);
            g.webview->remove_ProcessFailed(g.processFailedToken);
            g.controller->remove_AcceleratorKeyPressed(g.acceleratorKeyToken);
            g.webview->remove_NavigationCompleted(g.navigationCompletedToken);
        }
        if (g.controller) g.controller->Close();
        DestroyWindow(hwnd);
        return 0;
    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(hwnd, message, wParam, lParam);
}
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, PWSTR, int show) {
    SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
    if (FAILED(CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED))) return 1;

    WNDCLASSEXW wc{ sizeof(wc) };
    wc.lpfnWndProc = WindowProc;
    wc.hInstance = instance;
    wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    wc.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);
    wc.lpszClassName = kClassName;
    if (!RegisterClassExW(&wc)) return 2;

    HWND window = CreateWindowExW(0, kClassName, kWindowTitle, WS_OVERLAPPEDWINDOW,
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
