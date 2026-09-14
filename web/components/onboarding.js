(function () {
  "use strict";
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>\"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[char]);
  async function refresh() {
    const center = document.getElementById("onboardingCenter");
    const steps = document.getElementById("onboardingSteps");
    const completion = document.getElementById("onboardingCompletion");
    if (!center || !steps || !completion) return;
    try {
      const response = await fetch("/api/onboarding", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("onboarding indisponível");
      const payload = await response.json();
      const guide = payload && payload.guide;
      if (!guide || !Array.isArray(guide.steps)) throw new Error("guia inválido");
      steps.innerHTML = guide.steps.map((step, index) => `<div class="item"><div class="label">${index + 1} · ${escapeHtml(step.location)}</div><strong>${escapeHtml(step.title)}</strong><div class="muted">${escapeHtml(step.purpose)}</div><div class="muted">${escapeHtml(step.action_hint)}</div></div>`).join("");
      completion.textContent = escapeHtml(guide.completion_message || "");
      center.classList.remove("hidden");
    } catch (_) { center.classList.add("hidden"); }
  }
  window.ControladorOnboarding = Object.freeze({ refresh });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", refresh, { once: true }); else refresh();
})();
