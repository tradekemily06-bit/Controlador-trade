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

    POINT point{ GET_X_LPARAM(lParam), GET_Y_LPARAM(lParam) };
    if (message == WM_MOUSEWHEEL || message == WM_MOUSEHWHEEL) {
        // Win32 wheel lParam coordinates are screen-relative, unlike the
        // client-relative coordinates expected by SendMouseInput.
        if (!ScreenToClient(hostWindow, &point)) return HRESULT_FROM_WIN32(GetLastError());
    }

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
        capture = {};
        if (GetCapture() == hostWindow) ReleaseCapture();
        return sent;
    }

    if (!capture.captured && GetCapture() == hostWindow) ReleaseCapture();
    return S_OK;
}

// Keep the native cursor consistent with the cursor requested by WebView2
// while the pointer is over the visible panel clip.
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
