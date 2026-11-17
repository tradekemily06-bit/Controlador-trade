// Inject with ICoreWebView2.add_ScriptToExecuteOnDocumentCreated.
// Read-only DOM observer: it does not modify Streamlit markup, styles, or state.
// The native host owns the visible C control and sends {type:"controlador.toggle"}.
(() => {
  "use strict";
  if (window.__controladorHostBridgeInstalled) return;
  window.__controladorHostBridgeInstalled = true;

  const bridge = window.chrome && window.chrome.webview;
  if (!bridge) return;

  let scheduled = false;
  let lastPayload = "";

  const rectOf = (element) => {
    if (!element) return null;
    const rect = element.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return null;
    return {
      x: rect.left,
      y: rect.top,
      width: rect.width,
      height: rect.height,
      right: rect.right,
      bottom: rect.bottom
    };
  };

  const isVisible = (element) => {
    if (!element) return false;
    const style = window.getComputedStyle(element);
    return style.display !== "none" &&
      style.visibility !== "hidden" &&
      Number(style.opacity || "1") > 0 &&
      rectOf(element) !== null;
  };

  const publishLayout = () => {
    scheduled = false;
    const collapsedRoot = document.querySelector(".st-key-panel-toggle");
    const collapsedButton = collapsedRoot &&
      collapsedRoot.querySelector('[data-testid="stButton"] button, button');
    const expandedRoot = document.querySelector(".st-key-control-hub-shell");
    const expanded = isVisible(expandedRoot);
    const payload = {
      type: "controlador.panel.layout",
      version: 1,
      state: expanded ? "expanded" : "collapsed",
      viewport: {
        width: document.documentElement.clientWidth,
        height: document.documentElement.clientHeight,
        dpr: window.devicePixelRatio || 1
      },
      collapsedButton: rectOf(collapsedButton),
      expandedShell: expanded ? rectOf(expandedRoot) : null
    };
    const serialized = JSON.stringify(payload);
    if (serialized !== lastPayload) {
      lastPayload = serialized;
      bridge.postMessage(payload);
    }
  };

  const schedule = () => {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(publishLayout);
  };

  const clickStreamlitToggle = () => {
    const expandedRoot = document.querySelector(".st-key-control-hub-shell");
    const collapsedRoot = document.querySelector(".st-key-panel-toggle");
    const expanded = isVisible(expandedRoot);
    const root = expanded ? expandedRoot : collapsedRoot;
    if (!root) return;
    const buttons = Array.from(root.querySelectorAll("button"));
    const toggle = buttons.find((button) => button.textContent.trim() === "C");
    if (toggle && !toggle.disabled) toggle.click();
    schedule();
  };

  bridge.addEventListener("message", (event) => {
    if (event.data && event.data.type === "controlador.toggle") {
      clickStreamlitToggle();
    }
  });

  const mutations = new MutationObserver(schedule);
  const startObserving = () => {
    if (!document.documentElement) return;
    mutations.observe(document.documentElement, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["class", "style", "aria-hidden"]
    });
    schedule();
  };

  window.addEventListener("resize", schedule, { passive: true });
  window.addEventListener("scroll", schedule, { passive: true, capture: true });
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", startObserving, { once: true });
  } else {
    startObserving();
  }
})();
