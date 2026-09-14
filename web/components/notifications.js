(() => {
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const bySeverity = (items, severity) => (Array.isArray(items) ? items : []).filter((item) => item.severity === severity);

  function renderItem(item) {
    const blocking = item.blocking ? ' · BLOQUEANTE' : '';
    return `<div class="item"><b>${esc(item.title)}</b><br><span class="muted">${esc(item.message)}</span><br><span class="label">${esc(item.kind)} · ${esc(item.severity)}${blocking}</span></div>`;
  }

  async function refreshNotifications() {
    const response = await fetch('/api/notifications');
    if (!response.ok) throw new Error('Falha ao carregar notificações');
    const data = await response.json();
    const items = Array.isArray(data.items) ? data.items : [];
    const critical = bySeverity(items, 'CRITICAL');
    const important = bySeverity(items, 'IMPORTANT');
    const badge = document.getElementById('notificationBadge');
    const criticalBox = document.getElementById('notificationCritical');
    const importantBox = document.getElementById('notificationImportant');
    const expand = document.getElementById('notificationExpand');

    if (!badge || !criticalBox || !importantBox) return data;
    badge.textContent = String(data.count ?? items.length);
    badge.classList.toggle('hidden', items.length === 0);
    criticalBox.innerHTML = critical.map(renderItem).join('');
    importantBox.innerHTML = important.map(renderItem).join('');
    expand?.classList.toggle('hidden', items.length === 0);
    if (!items.length) {
      importantBox.innerHTML = '<div class="muted">Nenhuma notificação importante no momento.</div>';
    }
    return data;
  }

  window.ControladorNotifications = Object.freeze({ refresh: refreshNotifications });
})();
