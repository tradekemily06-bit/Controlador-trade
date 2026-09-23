(function () {
  "use strict";
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>\"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[char]);

  async function refresh(force = false) {
    const center = document.getElementById("onboardingCenter");
    const steps = document.getElementById("onboardingSteps");
    const completion = document.getElementById("onboardingCompletion");
    const close = document.getElementById("onboardingClose");
    if (!center || !steps || !completion) return;
    try {
      const response = await fetch("/api/onboarding", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("onboarding indisponível");
      const payload = await response.json();
      const guide = payload && payload.guide;
      if (!guide || !Array.isArray(guide.steps) || guide.execution_authorized !== false) throw new Error("guia inválido");
      steps.innerHTML = guide.steps.map((step, index) => `<div class="item"><div class="label">${index + 1} · ${escapeHtml(step.location)}</div><strong>${escapeHtml(step.title)}</strong><div class="muted">${escapeHtml(step.purpose)}</div><div class="muted">${escapeHtml(step.action_hint)}</div></div>`).join("");
      completion.textContent = escapeHtml(guide.completion_message || "");
      center.classList.remove("hidden");
      close?.addEventListener("click", () => { center.classList.add("hidden"); }, { once: true });
    } catch (_) {
      center.classList.add("hidden");
    }
  }

  function installReopenControl() {
    if (document.getElementById("onboardingReopenControl")) return;
    const config = document.getElementById("config");
    const grid = config?.nextElementSibling;
    if (!grid) return;
    const card = document.createElement("article");
    card.className = "card wide";
    card.id = "onboardingReopenControl";
    card.innerHTML = '<div class="module-title">Modo de Usar</div><div class="muted">Reabra o guia de utilização quando quiser. Ele é apenas educativo e não autoriza execução.</div><button class="btn small alt" id="onboardingReopen" type="button" style="margin-top:10px">ABRIR MODO DE USAR</button>';
    grid.appendChild(card);
    document.getElementById("onboardingReopen")?.addEventListener("click", () => refresh(true));
  }

  window.ControladorOnboarding = Object.freeze({ refresh, reopen: () => refresh(true) });
  const boot = () => { installReopenControl(); refresh(); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true }); else boot();
})();
