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
    return 0;
}
