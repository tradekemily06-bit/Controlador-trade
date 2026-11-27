# Mobile and cross-device compatibility contract

## Product requirement

The same Controlador Trading account and server-side data must be usable from phones, tablets and desktop computers. This is one web application/PWA, not separate Android, iOS and desktop products. Device identifiers are never user identities: tenant and subject ownership must come only from the verified server-side authentication context.

The approved Lovable interface is the visual source of truth. Connecting this capability must not rename, reorder, recolor, resize or redesign its existing areas. Responsive behavior may adapt layout to viewport size only when the existing frontend already supports it or after the owner explicitly approves a visual change.

## Meaning of “works on any device”

No web application can guarantee full feature parity on every device ever made. Browser engines, OS versions, hardware, privacy settings and vendor push policies differ. The compatibility goal is:

1. Core app access and account data work in a standards-compliant modern browser over HTTPS.
2. Layout remains usable at narrow phone, tablet, laptop and desktop viewport widths without horizontal overflow or inaccessible controls.
3. PWA installation is offered only where the browser supports it; otherwise the same app remains usable as a normal website.
4. Push notifications are enabled only where the OS/browser supports them and the user grants permission. Unsupported devices retain the in-app notification inbox and may use supported fallback channels.
5. Unsupported optional capabilities never block login, account access or core read-only analysis.

## Target browser matrix (must be verified on real devices)

| Device class | Primary browser target | Core web app | PWA install | Push while app is closed |
|---|---|---|---|---|
| Android phone/tablet | Current and previous two major Chrome releases | Required | Where browser supports install | Where Web Push is supported and permission granted |
| iPhone | Current and previous two supported iOS major releases, Safari | Required | Add to Home Screen where supported | iOS 16.4+ installed web app, permission granted; subject to Apple policy |
| iPad | Current and previous two supported iPadOS major releases, Safari | Required | Add to Home Screen where supported | Same iOS/iPadOS web-push constraints; validate on device |
| Windows desktop | Current and previous two Chrome and Edge major releases; Firefox current/ESR | Required | Browser-dependent | Browser/OS-dependent |
| macOS desktop | Current and previous two Safari and Chrome major releases | Required | Browser-dependent | Browser/OS-dependent |
| Other standards-based browsers | Best-effort progressive enhancement | Required where modern HTML, CSS, JS and HTTPS are supported | Feature-detected | Feature-detected |

This is a test target, not a claim that all rows have passed. Browser/OS support changes over time and must be rechecked before release.

## Capability detection and graceful fallback

The frontend must feature-detect, not infer support from user-agent strings:

- Service Worker: navigator.serviceWorker.
- Secure context: window.isSecureContext.
- Push: PushManager and Notification availability.
- Notification permission: request only after a clear user action and explain why.
- Install prompt: use the browser's supported install affordance; never require installation to use the app.
- Network state: online/offline indicators are advisory only; never present stale cached market data as current.

The current service worker intentionally caches only the public app icon. It does not cache authenticated API responses, fiscal records, market candles, decisions, conversations, access tokens or notification contents. Offline mode therefore does not promise access to live data or private records. When offline, the UI must clearly mark live analysis as unavailable rather than replaying stale values as current.

## Responsive acceptance tests

Before production release, validate at minimum these viewport classes: 320x640, 360x800, 390x844, 430x932, 768x1024, 1024x768, 1366x768 and 1920x1080.

For each class verify: no horizontal page overflow; all seven existing areas remain reachable; controls are not hidden behind safe-area insets, browser chrome or the on-screen keyboard; charts and tables remain readable; dialogs, menus and notification inbox work by touch and keyboard; text zoom does not make essential actions unreachable; orientation changes do not lose the session or corrupt input.

Do not claim responsive validation from viewport emulation alone. At least one real Android phone and one real iPhone/iPad must be included before production sign-off.

## Shared account and data acceptance tests

- Sign in on two different device classes with the same account; verify the same tenant-owned preferences, notification inbox and permitted records are shown.
- Change a preference on device A and verify it appears on device B after server confirmation.
- Sign out or revoke a session on one device; verify that device can no longer access protected data.
- Verify that one user's device registration, push endpoint, notifications, conversations and fiscal data cannot be read or modified by another tenant.
- Never use a device ID, local storage value, URL parameter or client-supplied tenant ID as proof of ownership.
- Browser storage may hold non-secret presentation preferences only. Provider secrets, shared bearer tokens and long-lived credentials must remain server-side.

## Push delivery acceptance tests

Push is optional and per-device. Each device must have its own authenticated subscription lifecycle: register, rotate/update, revoke on logout or permission loss, expire invalid endpoints, and isolate subscription ownership by trusted tenant/subject. Subscription endpoints and keys are sensitive capability data and require protected storage and access controls.

Before enabling push: deploy the frontend assets on the same HTTPS origin; connect web/pwa-registration.js to the deployed frontend shell without changing the approved visual layout; provide install-appropriate raster icons (including Apple touch icon and 192/512 PNG variants) in addition to SVG; implement authenticated per-device subscription registration and revocation; provision VAPID keys and Web Push sender credentials only in server-side secret storage; run the outbox dispatcher as a hosted worker independent of browser/device lifetime; send privacy-minimal payloads and fetch private details only after authenticated app launch; test delivery, click-through, expiry, logout/revocation and tenant isolation on real Android and Apple devices.

The current repository has PWA foundation assets and a generic push event handler, but it does not yet have the production subscription registry, protected endpoint/key storage, VAPID sender, deployed frontend integration or real-device push evidence. Therefore push delivery while the app is closed is NOT enabled.

## Release gate

Do not label the app “compatible with all devices” or “push notifications active” until the real-device matrix, authentication/session tests, responsive checks, PWA installation tests and push isolation/delivery tests have passed. Until then, describe it as a cross-device web foundation in preparation. Keep REAL trading and all money movement disabled.
