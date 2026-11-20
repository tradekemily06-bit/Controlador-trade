#include "layout_contract.h"
#include "native_input_contract.h"

#include <cassert>

using namespace controlador::host;

int main() {
    const auto move = TranslateMouseMessage(WM_MOUSEMOVE, 0);
    assert(move.supported && move.kind == COREWEBVIEW2_MOUSE_EVENT_KIND_MOVE);

    const auto leave = TranslateMouseMessage(WM_MOUSELEAVE, 0);
    assert(leave.supported && leave.kind == COREWEBVIEW2_MOUSE_EVENT_KIND_LEAVE);

    const auto leftDown = TranslateMouseMessage(WM_LBUTTONDOWN, 0);
    assert(leftDown.supported && leftDown.kind == COREWEBVIEW2_MOUSE_EVENT_KIND_LEFT_BUTTON_DOWN);
    const auto leftUp = TranslateMouseMessage(WM_LBUTTONUP, 0);
    assert(leftUp.supported && leftUp.kind == COREWEBVIEW2_MOUSE_EVENT_KIND_LEFT_BUTTON_UP);

    const auto rightDown = TranslateMouseMessage(WM_RBUTTONDOWN, 0);
    assert(rightDown.supported && rightDown.kind == COREWEBVIEW2_MOUSE_EVENT_KIND_RIGHT_BUTTON_DOWN);
    const auto rightUp = TranslateMouseMessage(WM_RBUTTONUP, 0);
    assert(rightUp.supported && rightUp.kind == COREWEBVIEW2_MOUSE_EVENT_KIND_RIGHT_BUTTON_UP);

    const auto middleDown = TranslateMouseMessage(WM_MBUTTONDOWN, 0);
    assert(middleDown.supported && middleDown.kind == COREWEBVIEW2_MOUSE_EVENT_KIND_MIDDLE_BUTTON_DOWN);
    const auto middleUp = TranslateMouseMessage(WM_MBUTTONUP, 0);
    assert(middleUp.supported && middleUp.kind == COREWEBVIEW2_MOUSE_EVENT_KIND_MIDDLE_BUTTON_UP);

    const auto wheel = TranslateMouseMessage(WM_MOUSEWHEEL, MAKEWPARAM(0, 120));
    assert(wheel.supported && wheel.kind == COREWEBVIEW2_MOUSE_EVENT_KIND_WHEEL);
    assert(static_cast<LONG>(wheel.mouseData) == 120);

    const auto horizontal = TranslateMouseMessage(WM_MOUSEHWHEEL, MAKEWPARAM(0, -120));
    assert(horizontal.supported &&
        horizontal.kind == COREWEBVIEW2_MOUSE_EVENT_KIND_HORIZONTAL_WHEEL);
    assert(static_cast<LONG>(horizontal.mouseData) == -120);

    const auto unsupported = TranslateMouseMessage(WM_KEYDOWN, 0);
    assert(!unsupported.supported);


    PhysicalLayout layout{};
    layout.accepted = true;
    layout.webViewVisible = true;
    layout.clip = {10, 10, 110, 110};
    assert(ShouldForwardMouseLeave(layout));
    auto collapsedLayout = layout;
    collapsedLayout.webViewVisible = false;
    assert(!ShouldForwardMouseLeave(collapsedLayout));

    MouseCaptureState capture{};
    POINT inside{50, 50};
    POINT outside{150, 150};

    assert(ShouldForwardMouseInput(layout, inside, WM_LBUTTONDOWN, capture));
    assert(capture.captured);
    assert(ShouldForwardMouseInput(layout, outside, WM_MOUSEMOVE, capture));
    assert(ShouldForwardMouseInput(layout, outside, WM_LBUTTONUP, capture));
    assert(!capture.captured);
    assert(!ShouldForwardMouseInput(layout, outside, WM_MOUSEMOVE, capture));

    // A second button pressed during a captured drag must also be released
    // before routing returns to the host application.
    assert(ShouldForwardMouseInput(layout, inside, WM_LBUTTONDOWN, capture));
    assert(ShouldForwardMouseInput(layout, inside, WM_RBUTTONDOWN, capture));
    assert(ShouldForwardMouseInput(layout, outside, WM_LBUTTONUP, capture));
    assert(capture.captured);
    assert(ShouldForwardMouseInput(layout, outside, WM_RBUTTONUP, capture));
    assert(!capture.captured);

    capture.captured = true;
    capture.pressedButtons = 3;
    ResetMouseCaptureState(capture);
    assert(!capture.captured && capture.pressedButtons == 0);

    return 0;
}
