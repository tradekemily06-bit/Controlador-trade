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

    return 0;
}
