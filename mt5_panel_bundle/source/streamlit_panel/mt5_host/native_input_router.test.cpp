#include "native_input_router.h"
#include <cassert>

using namespace controlador::host;

int main() {
    PhysicalLayout layout{};
    layout.accepted = true;
    layout.webViewVisible = true;
    layout.clip = {20, 30, 220, 230};

    assert(IsInsideClip(layout, POINT{20, 30}));
    assert(IsInsideClip(layout, POINT{219, 229}));
    assert(!IsInsideClip(layout, POINT{220, 230}));

    const auto move = TranslateMouseMessage(WM_MOUSEMOVE, 0);
    assert(move.supported && move.kind == COREWEBVIEW2_MOUSE_EVENT_KIND_MOVE);

    const auto wheel = TranslateMouseMessage(WM_MOUSEWHEEL, MAKEWPARAM(0, 120));
    assert(wheel.supported && static_cast<LONG>(wheel.mouseData) == 120);

    MouseCaptureState capture{};
    capture.captured = true;
    capture.pressedButtons = 0x03; // left + right
    RecordMouseButtonRelease(capture, 0x01, E_FAIL);
    assert(!capture.captured);
    assert(capture.pressedButtons == 0x03);
    assert(capture.releasePending);
    RecordMouseButtonRelease(capture, 0x02, S_OK);
    assert(capture.pressedButtons == 0x01);
    assert(capture.releasePending);
    RecordMouseButtonRelease(capture, 0x01, S_OK);
    assert(capture.pressedButtons == 0);
    assert(!capture.releasePending);
    ResetMouseCaptureState(capture);
    assert(!capture.captured && capture.pressedButtons == 0 && !capture.releasePending);
    return 0;
}
