/* Web Push service worker. Deploy on the frontend origin at /pwa/service-worker.js. */
self.addEventListener("push", (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (_) {
    payload = { title: "Controlador", message: "Você recebeu uma nova notificação." };
  }
  const title = typeof payload.title === "string" && payload.title.trim()
    ? payload.title : "Controlador";
  const body = typeof payload.message === "string" ? payload.message : "";
  const tag = typeof payload.idempotency_key === "string"
    ? payload.idempotency_key
    : (typeof payload.notification_id === "string" ? payload.notification_id : "controlador-event");

  event.waitUntil(self.registration.showNotification(title, {
    body,
    tag,
    renotify: false,
    data: {
      notification_id: payload.notification_id || null,
      kind: payload.kind || null,
      severity: payload.severity || null,
    },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil((async () => {
    const openClients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of openClients) {
      if ("focus" in client) {
        await client.focus();
        return;
      }
    }
    if (self.clients.openWindow) await self.clients.openWindow("/");
  })());
});
