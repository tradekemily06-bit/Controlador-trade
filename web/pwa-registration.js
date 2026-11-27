/* Include this file from the deployed frontend shell after the PWA assets
 * are hosted at the application origin. It does not change visual layout.
 * All capabilities are feature-detected; unsupported features degrade gracefully.
 */
(() => {
  const isStandalone = () => {
    const mediaStandalone = typeof window.matchMedia === "function" &&
      window.matchMedia("(display-mode: standalone)").matches;
    return mediaStandalone || navigator.standalone === true;
  };

  const state = {
    supported: "serviceWorker" in navigator,
    secure_context: window.isSecureContext === true,
    registration: "NOT_STARTED",
    push_supported: "PushManager" in window && "Notification" in window,
    push_permission: "Notification" in window ? Notification.permission : "UNSUPPORTED",
    installed: isStandalone(),
    online: navigator.onLine !== false,
    install_prompt: "UNAVAILABLE",
    error: null
  };

  const publish = () => {
    window.ControladorPWAStatus = Object.freeze({ ...state });
    window.dispatchEvent(new CustomEvent("controlador:pwa-status", {
      detail: window.ControladorPWAStatus
    }));
  };

  window.addEventListener("online", () => {
    state.online = true;
    publish();
  });
  window.addEventListener("offline", () => {
    state.online = false;
    publish();
  });
  window.addEventListener("beforeinstallprompt", () => {
    state.install_prompt = "AVAILABLE";
    publish();
  });
  window.addEventListener("appinstalled", () => {
    state.installed = true;
    state.install_prompt = "UNAVAILABLE";
    publish();
  });

  if (!state.supported || !state.secure_context) {
    state.registration = "UNAVAILABLE";
    state.error = state.secure_context ? "SERVICE_WORKER_UNSUPPORTED" : "HTTPS_REQUIRED";
    publish();
    return;
  }

  navigator.serviceWorker.register("/service-worker.js", { scope: "/" })
    .then((registration) => {
      state.registration = "REGISTERED";
      state.scope = registration.scope;
      state.installed = isStandalone();
      publish();
    })
    .catch(() => {
      state.registration = "FAILED";
      state.error = "SERVICE_WORKER_REGISTRATION_FAILED";
      publish();
    });
  publish();
})();
