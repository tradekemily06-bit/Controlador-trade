(function () {
  "use strict";
  const STORAGE_KEY = "controlador:first-use:onboarding-complete";
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>\"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[char]);

  async function refresh(force = false) {
    const center = document.getElementById("onboardingCenter");
    const steps = document.getElementById("onboardingSteps");
    const completion = document.getElementById("onboardingCompletion");
    const close = document.getElementById("onboardingClose");
    if (!center || !steps || !completion) return;
    if (!force && localStorage.getItem(STORAGE_KEY) === "true") return;
    try {
      const response = await fetch("/api/onboarding", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("onboarding indisponível");
      const payload = await response.json();
      const guide = payload && payload.guide;
      if (!guide || !Array.isArray(guide.steps) || guide.execution_authorized !== false) throw new Error("guia inválido");
      steps.innerHTML = guide.steps.map((step, index) => `<div class="item"><div class="label">${index + 1} · ${escapeHtml(step.location)}</div><strong>${escapeHtml(step.title)}</strong><div class="muted">${escapeHtml(step.purpose)}</div><div class="muted">${escapeHtml(step.action_hint)}</div></div>`).join("");
      completion.textContent = escapeHtml(guide.completion_message || "");
      center.classList.remove("hidden");
      close?.addEventListener("click", () => { localStorage.setItem(STORAGE_KEY, "true"); center.classList.add("hidden"); }, { once: true });
    } catch (_) {
      center.classList.add("hidden");
    }
  }

  async function loadPsychologyPreferences() {
    const enabled = document.getElementById("psychologyEnabled");
    const collection = document.getElementById("psychologyCollection");
    const status = document.getElementById("psychologySettingsStatus");
    if (!enabled || !collection || !status) return;
    try {
      const response = await fetch("/api/preferences", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("preferências indisponíveis");
      const payload = await response.json();
      const prefs = payload?.preferences || {};
      enabled.checked = prefs.psychology_enabled !== false;
      collection.checked = prefs.psychology_data_collection_enabled !== false;
      collection.disabled = !enabled.checked;
      status.textContent = enabled.checked ? "Psicologia ativa. A camada de segurança continua independente." : "Psicologia desativada. Risco, segurança, auditoria e bloqueios continuam ativos.";
    } catch (_) {
      status.textContent = "Não foi possível carregar as preferências de psicologia.";
    }
  }

  async function savePsychologyPreferences() {
    const enabled = document.getElementById("psychologyEnabled");
    const collection = document.getElementById("psychologyCollection");
    const status = document.getElementById("psychologySettingsStatus");
    if (!enabled || !collection || !status) return;
    const requestedEnabled = enabled.checked;
    collection.disabled = !requestedEnabled;
    status.textContent = "Salvando...";
    try {
      const response = await fetch("/api/preferences", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ psychology_enabled: requestedEnabled, psychology_data_collection_enabled: collection.checked })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.error || "não foi possível salvar");
      const prefs = payload?.preferences || {};
      enabled.checked = prefs.psychology_enabled !== false;
      collection.checked = prefs.psychology_data_collection_enabled !== false;
      collection.disabled = !enabled.checked;
      status.textContent = enabled.checked ? "Psicologia ativa." : "Psicologia desativada. Proteções essenciais continuam ativas.";
    } catch (error) {
      status.textContent = `Falha ao salvar: ${escapeHtml(error.message)}`;
      await loadPsychologyPreferences();
    }
  }

  function installPsychologyControl() {
    if (document.getElementById("psychologySettingsControl")) return;
    const config = document.getElementById("config");
    const grid = config?.nextElementSibling;
    if (!grid) return;
    const card = document.createElement("article");
    card.className = "card wide";
    card.id = "psychologySettingsControl";
    card.innerHTML = '<div class="module-title">Psicologia do Trader</div><div class="muted">Controle a camada comportamental sem alterar o núcleo de decisão, Risk Gate ou segurança.</div><div class="controls"><label class="check"><input id="psychologyEnabled" type="checkbox"> Ativar análise psicológica</label><label class="check"><input id="psychologyCollection" type="checkbox"> Permitir registro de dados comportamentais para histórico e aprendizado</label><button class="btn alt" id="savePsychology" type="button">SALVAR PSICOLOGIA</button><div id="psychologySettingsStatus" class="muted">Carregando...</div></div>';
    grid.appendChild(card);
    document.getElementById("savePsychology")?.addEventListener("click", savePsychologyPreferences);
    loadPsychologyPreferences();
  }

  function installReopenControl() {
    if (document.getElementById("onboardingReopenControl")) return;
    const config = document.getElementById("config");
    const grid = config?.nextElementSibling;
    if (!grid) return;
    const card = document.createElement("article");
    card.className = "card wide";
    card.id = "onboardingReopenControl";
    card.innerHTML = '<div class="module-title">Modo de Usar</div><div class="muted">Reabra o guia de primeira utilização quando quiser. Ele é apenas educativo e não autoriza execução.</div><button class="btn small alt" id="onboardingReopen" type="button" style="margin-top:10px">ABRIR MODO DE USAR</button>';
    grid.appendChild(card);
    document.getElementById("onboardingReopen")?.addEventListener("click", () => refresh(true));
  }

  window.ControladorOnboarding = Object.freeze({ refresh, reopen: () => refresh(true) });
  const boot = () => { installPsychologyControl(); installReopenControl(); refresh(); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true }); else boot();
})();
