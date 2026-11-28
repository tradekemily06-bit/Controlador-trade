/* Behavior-only browser helper. It does not render or modify application UI. */
(() => {
  "use strict";

  const DEVICE_KEY = "controlador.push.device_id.v1";
  const DEFAULT_WORKER = "/pwa/service-worker.js";

  function decodeVapidKey(value) {
    if (typeof value !== "string" || !value.trim()) {
      throw new Error("Chave pública VAPID não configurada.");
    }
    const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized + "=".repeat((4 - normalized.length % 4) % 4);
    const raw = atob(padded);
    return Uint8Array.from(raw, (character) => character.charCodeAt(0));
  }

  function deviceId() {
    let id = localStorage.getItem(DEVICE_KEY);
    if (!id) {
      if (!globalThis.crypto || typeof globalThis.crypto.randomUUID !== "function") {
        throw new Error("Este navegador não oferece geração segura de identificador.");
      }
      id = globalThis.crypto.randomUUID();
      localStorage.setItem(DEVICE_KEY, id);
    }
    return id;
  }

  function endpoint(apiBaseUrl, suffix = "") {
    const url = new URL("/api/push/subscriptions" + suffix, apiBaseUrl || window.location.origin);
    if (url.protocol !== "https:" && url.hostname !== "localhost" && url.hostname !== "127.0.0.1") {
      throw new Error("A API de notificações deve usar HTTPS.");
    }
    return url.toString();
  }

  async function apiRequest(url, accessToken, options = {}) {
    if (typeof accessToken !== "string" || !accessToken.trim()) {
      throw new Error("Sessão autenticada do aplicativo não encontrada.");
    }
    const response = await fetch(url, {
      ...options,
      headers: {
        Authorization: "Bearer " + accessToken,
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {}),
      },
      cache: "no-store",
      credentials: "omit",
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || "Não foi possível atualizar as notificações.");
    }
    return response.status === 204 ? null : response.json();
  }

  async function enable({ accessToken, vapidPublicKey, apiBaseUrl, workerPath = DEFAULT_WORKER }) {
    if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
      throw new Error("Este navegador não oferece suporte a notificações push.");
    }
    const permission = await Notification.requestPermission();
    if (permission !== "granted") return { enabled: false, permission };

    const registration = await navigator.serviceWorker.register(workerPath, { scope: "/pwa/" });
    await navigator.serviceWorker.ready;
    let subscription = await registration.pushManager.getSubscription();
    if (!subscription) {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: decodeVapidKey(vapidPublicKey),
      });
    }

    const result = await apiRequest(endpoint(apiBaseUrl), accessToken, {
      method: "POST",
      body: JSON.stringify({
        device_id: deviceId(),
        subscription: subscription.toJSON(),
      }),
    });
    return { enabled: true, permission, device: result.device };
  }

  async function disable({ accessToken, apiBaseUrl }) {
    const id = localStorage.getItem(DEVICE_KEY);
    if (!id) return { revoked: false, reason: "NO_LOCAL_DEVICE" };

    const result = await apiRequest(endpoint(apiBaseUrl, "/" + encodeURIComponent(id)), accessToken, {
      method: "DELETE",
    });
    const registration = await navigator.serviceWorker.getRegistration("/pwa/");
    const subscription = registration && await registration.pushManager.getSubscription();
    if (subscription) await subscription.unsubscribe();
    localStorage.removeItem(DEVICE_KEY);
    return result.device;
  }

  async function list({ accessToken, apiBaseUrl }) {
    return apiRequest(endpoint(apiBaseUrl), accessToken);
  }

  window.ControladorPush = Object.freeze({ enable, disable, list });
})();
