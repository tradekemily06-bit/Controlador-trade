#pragma once

#include <windows.h>
#include <WebView2.h>
#include <cstdint>

namespace controlador::host {

struct MouseInput {
    bool supported{};
    COREWEBVIEW2_MOUSE_EVENT_KIND kind{COREWEBVIEW2_MOUSE_EVENT_KIND_MOVE};
    UINT32 mouseData{};
    COREWEBVIEW2_MOUSE_EVENT_VIRTUAL_KEYS virtualKeys{COREWEBVIEW2_MOUSE_EVENT_VIRTUAL_KEYS_NONE};
};

inline MouseInput TranslateMouseMessage(UINT message, WPARAM wParam) noexcept {
    MouseInput result{};
    result.virtualKeys = static_cast<COREWEBVIEW2_MOUSE_EVENT_VIRTUAL_KEYS>(
        GET_KEYSTATE_WPARAM(wParam));

    switch (message) {
    case WM_MOUSEMOVE:
        result.kind = COREWEBVIEW2_MOUSE_EVENT_KIND_MOVE;
        break;
    case WM_MOUSELEAVE:
        result.kind = COREWEBVIEW2_MOUSE_EVENT_KIND_LEAVE;
        break;
    case WM_LBUTTONDOWN:
        result.kind = COREWEBVIEW2_MOUSE_EVENT_KIND_LEFT_BUTTON_DOWN;
        break;
    case WM_LBUTTONUP:
        result.kind = COREWEBVIEW2_MOUSE_EVENT_KIND_LEFT_BUTTON_UP;
        break;
    case WM_RBUTTONDOWN:
        result.kind = COREWEBVIEW2_MOUSE_EVENT_KIND_RIGHT_BUTTON_DOWN;
        break;
    case WM_RBUTTONUP:
        result.kind = COREWEBVIEW2_MOUSE_EVENT_KIND_RIGHT_BUTTON_UP;
        break;
    case WM_MBUTTONDOWN:
        result.kind = COREWEBVIEW2_MOUSE_EVENT_KIND_MIDDLE_BUTTON_DOWN;
        break;
    case WM_MBUTTONUP:
        result.kind = COREWEBVIEW2_MOUSE_EVENT_KIND_MIDDLE_BUTTON_UP;
        break;
    case WM_MOUSEWHEEL:
        result.kind = COREWEBVIEW2_MOUSE_EVENT_KIND_WHEEL;
        result.mouseData = static_cast<UINT32>(GET_WHEEL_DELTA_WPARAM(wParam));
        break;
    case WM_MOUSEHWHEEL:
        result.kind = COREWEBVIEW2_MOUSE_EVENT_KIND_HORIZONTAL_WHEEL;
        result.mouseData = static_cast<UINT32>(GET_WHEEL_DELTA_WPARAM(wParam));
        break;
    default:
        return result;
    }

    result.supported = true;
    return result;
}

inline bool ShouldForwardMouseInput(
    const PhysicalLayout& layout, POINT hostClientPoint, UINT message) noexcept {
    const MouseInput input = TranslateMouseMessage(message, 0);
    return input.supported && IsInsideClip(layout, hostClientPoint);
}

} // namespace controlador::host
