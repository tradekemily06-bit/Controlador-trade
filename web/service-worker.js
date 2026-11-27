/* Controlador Trading PWA service worker.
 * Deliberately caches only the public application icon. Authenticated API
 * responses, market data, fiscal records, conversations and notifications
 * are never cached by this worker.
 */
"use strict";

const CACHE_NAME = "controlador-public-assets-v1";
const PUBLIC_ICON = new URL("./pwa/icon.svg", self.registration.scope).toString();

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.add(PUBLIC_ICON))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((key) => key.startsWith("controlador-public-assets-") && key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Never intercept API, authenticated data, navigation or arbitrary files.
  if (url.pathname.startsWith("/api/") || request.mode === "navigate") return;
  if (url.href !== PUBLIC_ICON) return;

  event.respondWith(
    caches.open(CACHE_NAME).then(async (cache) => {
      const cached = await cache.match(PUBLIC_ICON);
      return cached || fetch(request);
    })
  );
});

self.addEventListener("push", (event) => {
  // Generic notification content only. Private details are fetched after
  // the user opens the authenticated application.
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (_) {
    payload = {};
  }
  const title = typeof payload.title === "string" && payload.title.length <= 80
    ? payload.title : "Controlador Trading";
  const body = typeof payload.body === "string" && payload.body.length <= 160
    ? payload.body : "Há uma atualização importante no seu ecossistema.";
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: "./pwa/icon.svg",
      badge: "./pwa/icon.svg",
      tag: typeof payload.event_id === "string" ? payload.event_id.slice(0, 100) : "controlador-update",
      data: { url: "/" },
      renotify: false
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true })
      .then((clients) => {
        const existing = clients.find((client) => new URL(client.url).origin === self.location.origin);
        if (existing) return existing.focus();
        return self.clients.openWindow("/");
      })
  );
});
