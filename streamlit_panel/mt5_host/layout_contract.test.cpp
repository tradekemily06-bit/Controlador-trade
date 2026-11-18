#include "layout_contract.h"

#include <cassert>
#include <iostream>

using controlador::host::BuildWindowRegionRects;
using controlador::host::IsInsideClip;
using controlador::host::LayoutMessage;
using controlador::host::ValidateLayout;

int main() {
    LayoutMessage expanded{1, 1280.0, 720.0, 1.5, true, {16.0, 200.0, 420.0, 460.0}};
    auto layout = ValidateLayout(expanded, 0, 1280.0, 720.0);
    assert(layout.accepted && layout.webViewVisible && layout.sequence == 1);
    assert(layout.clip.left == 24 && layout.clip.top == 300);
    assert(layout.clip.right == 654 && layout.clip.bottom == 990);
    assert(IsInsideClip(layout, POINT{24, 300}));
    assert(!IsInsideClip(layout, POINT{23, 300}));
    assert(!IsInsideClip(layout, POINT{654, 500}));

    auto stale = ValidateLayout(expanded, 1, 1280.0, 720.0);
    assert(!stale.accepted && !stale.webViewVisible);

    LayoutMessage collapsed{2, 1280.0, 720.0, 1.0, false, {}};
    auto closed = ValidateLayout(collapsed, 1, 1280.0, 720.0);
    assert(closed.accepted && !closed.webViewVisible);

    LayoutMessage invalidDpr{3, 1280.0, 720.0, 0.0, true, {0, 0, 200, 200}};
    assert(!ValidateLayout(invalidDpr, 2, 1280.0, 720.0).accepted);

    LayoutMessage outside{4, 1280.0, 720.0, 1.0, true, {1200, 650, 100, 100}};
    assert(!ValidateLayout(outside, 2, 1280.0, 720.0).accepted);

    LayoutMessage mismatch{5, 1280.0, 720.0, 1.0, true, {0, 0, 100, 100}};
    assert(!ValidateLayout(mismatch, 2, 1278.0, 720.0).accepted);

    std::cout << "Native layout validation, DPI conversion, stale-message rejection, and hit-test contract: OK\n";
}
