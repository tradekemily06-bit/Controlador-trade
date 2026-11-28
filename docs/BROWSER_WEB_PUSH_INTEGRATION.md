# Browser Web Push integration without UI changes

These assets provide browser behavior for the notification settings already present in the frontend. They do not create a screen or change the approved interface.

## Deployment

1. Deploy `web/pwa/service-worker.js` on the frontend's own HTTPS origin at `/pwa/service-worker.js`. A service worker must be served from the same origin as the pages it controls; an API hosted on another domain cannot control the Lovable frontend.
2. Load `web/pwa/push-client.js` in the existing frontend bundle. The existing notification settings can call `ControladorPush.enable({ accessToken, vapidPublicKey, apiBaseUrl })` after the user explicitly enables notifications.
3. Supply only the public VAPID key to the browser. Never expose the VAPID private key or the AES subscription-encryption key.
4. Use the same authenticated bearer token as the standalone API. The helper uses `credentials: omit`; it does not rely on ambient cookies.
5. If the API has a different origin, allow the exact frontend origin in `CONTROLADOR_ALLOWED_ORIGINS`.
6. Use `ControladorPush.disable({ accessToken, apiBaseUrl })` to revoke the server record before unsubscribing locally, and `ControladorPush.list(...)` to show device metadata.

## Delivery semantics

The service worker displays the notification title and message and uses the outbox idempotency key as the notification tag to reduce duplicate visible notifications. Clicking a notification focuses an existing app tab or opens the frontend root. It never sends a trade order.

## Remaining production requirements

These assets alone do not enable delivery. Production still requires a concrete shared durable encrypted subscription backend, real secret-manager integration, VAPID key pair, hosted outbox worker, deployment of these files to the Lovable frontend origin, and real-device tests on supported browsers and mobile OSes. Push delivery is best-effort and depends on browser, OS, permission, network and push-service availability; it is not a guarantee of continuous 24/7 operation.