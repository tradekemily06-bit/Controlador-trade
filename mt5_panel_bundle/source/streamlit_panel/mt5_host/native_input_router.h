#pragma once

#include "native_input_contract.h"

#include <windows.h>
#include <windowsx.h>
#include <WebView2.h>

namespace controlador::host {

// Route one native window message to the composition controller. Coordinates
// are kept in host-client pixels because the WebView visual spans the full
// viewport; the visual clip is enforced by the matching hit-test contract.
inline HRESULT RouteMouseMessage(
    HWND hostWindow,
    ICoreWebView2CompositionController* composition,
    const PhysicalLayout& layout,
    UINT message,
    WPARAM wParam,
    LPARAM lParam,
    MouseCaptureState& capture) noexcept
{
    if (!hostWindow || !composition) return E_POINTER;
    if (capture.releasePending) return E_ABORT;

    POINT point{ GET_X_LPARAM(lParam), GET_Y_LPARAM(lParam) };
    if (message == WM_MOUSEWHEEL || message == WM_MOUSEHWHEEL) {
        // Win32 wheel lParam coordinates are screen-relative, unlike the
        // client-relative coordinates expected by SendMouseInput.
        if (!ScreenToClient(hostWindow, &point)) return HRESULT_FROM_WIN32(GetLastError());
    }

    // Preserve the pre-event state until WebView2 confirms that the event was
    // accepted. In particular, a failed BUTTON_UP must remain eligible for a
    // cancellation release; a failed BUTTON_DOWN must not create a phantom press.
    const MouseCaptureState previousCapture = capture;

    // WM_MOUSELEAVE has no meaningful client coordinates; deliver it whenever
    // the clipped WebView is active so hover state cannot remain stuck.
    const bool forward = message == WM_MOUSELEAVE
        ? ShouldForwardMouseLeave(layout)
        : ShouldForwardMouseInput(layout, point, message, capture);
    if (!forward) return S_FALSE;

    if ((message == WM_LBUTTONDOWN || message == WM_RBUTTONDOWN ||
         message == WM_MBUTTONDOWN) && capture.captured) {
        SetCapture(hostWindow);
    }

    if (message == WM_MOUSEMOVE && IsInsideClip(layout, point)) {
        TRACKMOUSEEVENT tracking{ sizeof(TRACKMOUSEEVENT), TME_LEAVE, hostWindow, 0 };
        TrackMouseEvent(&tracking);
    }

    const MouseInput input = TranslateMouseMessage(message, wParam);
    if (!input.supported) return S_FALSE;

    const HRESULT sent = composition->SendMouseInput(
        input.kind, input.virtualKeys, input.mouseData, point);
    if (FAILED(sent)) {
        // Roll back speculative bookkeeping. The caller can then release any
        // button that WebView2 may still consider pressed.
        capture = previousCapture;
        return sent;
    }

    if (!capture.captured && GetCapture() == hostWindow) ReleaseCapture();
    return S_OK;
}

// Keep the native cursor consistent with the cursor requested by WebView2
// while the pointer is over the visible panel clip.
// Release any mouse button still held by WebView2 before native capture is
// cancelled or the panel is hidden. Clearing only host bookkeeping can leave
// the DOM believing a button is still down after WM_CANCELMODE/WM_CAPTURECHANGED.
inline HRESULT CancelMouseCapture(
    HWND hostWindow,
    ICoreWebView2CompositionController* composition,
    MouseCaptureState& capture) noexcept
{
    HRESULT firstFailure = S_OK;
    const std::uint8_t pressed = capture.pressedButtons;
    POINT point{};
    if (hostWindow && GetCursorPos(&point) && !ScreenToClient(hostWindow, &point)) point = {};

    const auto release = [&](std::uint8_t bit, COREWEBVIEW2_MOUSE_EVENT_KIND kind) {
        if ((pressed & bit) == 0) return;
        const HRESULT hr = composition
            ? composition->SendMouseInput(kind, COREWEBVIEW2_MOUSE_EVENT_VIRTUAL_KEYS_NONE, 0, point)
            : E_POINTER;
        RecordMouseButtonRelease(capture, bit, hr);
        if (FAILED(hr) && SUCCEEDED(firstFailure)) firstFailure = hr;
    };
    release(1, COREWEBVIEW2_MOUSE_EVENT_KIND_LEFT_BUTTON_UP);
    release(2, COREWEBVIEW2_MOUSE_EVENT_KIND_RIGHT_BUTTON_UP);
    release(4, COREWEBVIEW2_MOUSE_EVENT_KIND_MIDDLE_BUTTON_UP);

    capture.captured = false;
    capture.releasePending = capture.pressedButtons != 0;
    if (capture.pressedButtons == 0) ResetMouseCaptureState(capture);
    if (hostWindow && GetCapture() == hostWindow) ReleaseCapture();
    return firstFailure;
}

inline HRESULT ApplyWebViewCursor(
    ICoreWebView2CompositionController* composition,
    const PhysicalLayout& layout,
    POINT hostClientPoint) noexcept
{
    if (!composition) return E_POINTER;
    if (!IsInsideClip(layout, hostClientPoint)) return S_FALSE;

    HCURSOR cursor = nullptr;
    const HRESULT result = composition->get_Cursor(&cursor);
    if (SUCCEEDED(result) && cursor) SetCursor(cursor);
    return result;
}

} // namespace controlador::host
