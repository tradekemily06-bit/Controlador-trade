(() => {
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const state = document.getElementById('killSwitchState');
  const result = document.getElementById('killSwitchResult');
  const reason = document.getElementById('killSwitchReason');
  const button = document.getElementById('activateKillSwitch');
  async function refresh() {
    try {
      const response = await fetch('/api/kill-switch', { headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error('estado indisponível');
      const data = await response.json();
      const active = Boolean(data.enabled);
      state.textContent = active ? 'ATIVO' : 'LIVRE';
      state.className = active ? 'danger' : 'ok';
      button.disabled = active;
      if (active) {
        result.innerHTML = '<span class="danger">Execução permanece bloqueada. Motivo: ' + esc(data.reason || 'não informado') + '</span>';
      }
      return data;
    } catch (error) {
      state.textContent = 'BLOQUEADO';
      state.className = 'danger';
      button.disabled = true;
      result.textContent = 'Não foi possível verificar o Kill switch. O estado seguro permanece bloqueado.';
      return null;
    }
  }
  button?.addEventListener('click', async () => {
    const value = String(reason?.value || '').trim();
    if (!value) {
      result.textContent = 'Informe o motivo antes de ativar.';
      return;
    }
    button.disabled = true;
    try {
      const response = await fetch('/api/kill-switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'activate', reason: value })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'falha ao ativar');
      result.innerHTML = '<span class="danger"><b>KILL SWITCH ATIVO.</b> Novas execuções permanecem bloqueadas.</span>';
      await refresh();
    } catch (error) {
      result.innerHTML = '<span class="danger">Falha ao ativar: ' + esc(error.message) + '</span>';
      button.disabled = false;
    }
  });
  refresh();
  window.ControladorKillSwitch = Object.freeze({ refresh });
})();
