/* Include this file from the deployed frontend shell after the PWA assets
 * are hosted at the application origin. It does not change visual layout.
 */
(() => {
  const state = {
    supported: "serviceWorker" in navigator,
    secure_context: window.isSecureContext === true,
    registration: "NOT_STARTED",
    error: null
  };

  const publish = () => {
    window.ControladorPWAStatus = Object.freeze({ ...state });
    window.dispatchEvent(new CustomEvent("controlador:pwa-status", {
      detail: window.ControladorPWAStatus
    }));
  };

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
      publish();
    })
    .catch(() => {
      state.registration = "FAILED";
      state.error = "SERVICE_WORKER_REGISTRATION_FAILED";
      publish();
    });
  publish();
})();
