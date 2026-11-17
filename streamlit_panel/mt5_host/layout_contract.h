#pragma once

#include <windows.h>
#include <algorithm>
#include <cmath>
#include <cstdint>

namespace controlador::host {

struct CssRect {
    double x{};
    double y{};
    double width{};
    double height{};
};

struct LayoutMessage {
    std::uint64_t sequence{};
    double viewportWidth{};
    double viewportHeight{};
    double devicePixelRatio{};
    bool expanded{};
    CssRect expandedShell{};
};

struct PhysicalLayout {
    bool accepted{};
    bool webViewVisible{};
    std::uint64_t sequence{};
    RECT clip{}; // Host-client physical pixels; empty when collapsed or rejected.
};

inline LONG ToPhysical(double css, double dpr) {
    return static_cast<LONG>(std::llround(css * dpr));
}

// Fail closed: reject stale, malformed, off-viewport, or implausible DOM geometry.
// The caller must hide WebView2 and release input capture whenever accepted == false.
inline PhysicalLayout ValidateLayout(
    const LayoutMessage& message,
    std::uint64_t lastAcceptedSequence,
    double hostClientWidthCss,
    double hostClientHeightCss) noexcept
{
    PhysicalLayout result{};
    result.sequence = lastAcceptedSequence;

    if (message.sequence <= lastAcceptedSequence ||
        !std::isfinite(message.viewportWidth) ||
        !std::isfinite(message.viewportHeight) ||
        !std::isfinite(message.devicePixelRatio) ||
        message.viewportWidth <= 0 || message.viewportHeight <= 0 ||
        message.devicePixelRatio < 0.5 || message.devicePixelRatio > 8.0 ||
        !std::isfinite(hostClientWidthCss) || !std::isfinite(hostClientHeightCss) ||
        hostClientWidthCss <= 0 || hostClientHeightCss <= 0) {
        return result;
    }

    // DOM viewport must describe the same client area as the native host (1 CSS px tolerance).
    if (std::abs(message.viewportWidth - hostClientWidthCss) > 1.0 ||
        std::abs(message.viewportHeight - hostClientHeightCss) > 1.0) {
        return result;
    }

    result.accepted = true;
    result.sequence = message.sequence;
    result.webViewVisible = false;

    if (!message.expanded) {
        return result;
    }

    const auto& r = message.expandedShell;
    if (!std::isfinite(r.x) || !std::isfinite(r.y) ||
        !std::isfinite(r.width) || !std::isfinite(r.height) ||
        r.x < 0 || r.y < 0 || r.width <= 0 || r.height <= 0 ||
        r.width > message.viewportWidth || r.height > message.viewportHeight ||
        r.x + r.width > message.viewportWidth + 1.0 ||
        r.y + r.height > message.viewportHeight + 1.0) {
        result.accepted = false;
        result.sequence = lastAcceptedSequence;
        return result;
    }

    const double dpr = message.devicePixelRatio;
    result.clip = {
        ToPhysical(r.x, dpr),
        ToPhysical(r.y, dpr),
        ToPhysical(r.x + r.width, dpr),
        ToPhysical(r.y + r.height, dpr)
    };
    if (result.clip.right <= result.clip.left || result.clip.bottom <= result.clip.top) {
        result.accepted = false;
        result.sequence = lastAcceptedSequence;
        result.clip = {};
        return result;
    }

    result.webViewVisible = true;
    return result;
}

inline bool IsInsideClip(const PhysicalLayout& layout, POINT clientPoint) noexcept {
    return layout.accepted && layout.webViewVisible &&
        clientPoint.x >= layout.clip.left && clientPoint.x < layout.clip.right &&
        clientPoint.y >= layout.clip.top && clientPoint.y < layout.clip.bottom;
}

} // namespace controlador::host
