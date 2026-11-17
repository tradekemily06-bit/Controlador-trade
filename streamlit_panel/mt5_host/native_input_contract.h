#pragma once

#include "layout_contract.h"
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

struct MouseCaptureState {
    bool captured{};
    std::uint8_t pressedButtons{};
};

// A press that starts inside the clipped panel keeps routing move/up events to
// WebView2 until every pressed button is released, even when the pointer leaves
// the visible clip. This prevents a drag from becoming stuck in the web content.
inline bool ShouldForwardMouseInput(
    const PhysicalLayout& layout,
    POINT hostClientPoint,
    UINT message,
    MouseCaptureState& capture) noexcept {
    const MouseInput input = TranslateMouseMessage(message, 0);
    if (!input.supported) return false;

    constexpr std::uint8_t left = 1;
    constexpr std::uint8_t right = 2;
    constexpr std::uint8_t middle = 4;
    const bool inside = IsInsideClip(layout, hostClientPoint);

    auto buttonBit = [](UINT msg) -> std::uint8_t {
        switch (msg) {
        case WM_LBUTTONDOWN: case WM_LBUTTONUP: return left;
        case WM_RBUTTONDOWN: case WM_RBUTTONUP: return right;
        case WM_MBUTTONDOWN: case WM_MBUTTONUP: return middle;
        default: return 0;
        }
    };

    const bool isDown = message == WM_LBUTTONDOWN ||
        message == WM_RBUTTONDOWN || message == WM_MBUTTONDOWN;
    const bool isUp = message == WM_LBUTTONUP ||
        message == WM_RBUTTONUP || message == WM_MBUTTONUP;
    const std::uint8_t bit = buttonBit(message);

    if (isDown && (inside || capture.captured)) {
        capture.pressedButtons = static_cast<std::uint8_t>(capture.pressedButtons | bit);
        capture.captured = true;
        return true;
    }

    if (isUp && capture.captured) {
        const bool forward = (capture.pressedButtons & bit) != 0 || inside;
        capture.pressedButtons = static_cast<std::uint8_t>(capture.pressedButtons & ~bit);
        capture.captured = capture.pressedButtons != 0;
        return forward;
    }

    if (capture.captured &&
        (message == WM_MOUSEMOVE || message == WM_MOUSELEAVE)) return true;

    return inside;
}

} // namespace controlador::host
