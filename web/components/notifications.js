(() => {
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const bySeverity = (items, severity) => (Array.isArray(items) ? items : []).filter((item) => item.severity === severity);

  function renderItem(item) {
    const blocking = item.blocking ? ' · BLOQUEANTE' : '';
    return `<div class="item"><b>${esc(item.title)}</b><br><span class="muted">${esc(item.message)}</span><br><span class="label">${esc(item.kind)} · ${esc(item.severity)}${blocking}</span></div>`;
  }

  function renderLists(items, boxes) {
    const critical = bySeverity(items, 'CRITICAL');
    const important = bySeverity(items, 'IMPORTANT');
    const info = bySeverity(items, 'INFO');
    boxes.critical.innerHTML = critical.map(renderItem).join('');
    boxes.important.innerHTML = important.map(renderItem).join('');
    boxes.info.innerHTML = info.map(renderItem).join('');
    if (!items.length) {
      boxes.important.innerHTML = '<div class="muted">Nenhuma notificação importante no momento.</div>';
    }
  }

  async function refreshNotifications() {
    const response = await fetch('/api/notifications');
    if (!response.ok) throw new Error('Falha ao carregar notificações');
    const data = await response.json();
    const items = Array.isArray(data.items) ? data.items : [];
    const badge = document.getElementById('notificationBadge');
    const criticalBox = document.getElementById('notificationCritical');
    const importantBox = document.getElementById('notificationImportant');
    const infoBox = document.getElementById('notificationInfo');
    const expand = document.getElementById('notificationExpand');

    if (!badge || !criticalBox || !importantBox || !infoBox) return data;
    badge.textContent = String(data.count ?? items.length);
    badge.classList.toggle('hidden', items.length === 0);
    renderLists(items, { critical: criticalBox, important: importantBox, info: infoBox });
    if (expand) {
      expand.classList.toggle('hidden', items.length === 0);
      expand.textContent = 'VER TODAS';
      expand.onclick = async () => {
        if (!infoBox.classList.contains('hidden')) {
          infoBox.classList.add('hidden');
          expand.textContent = 'VER TODAS';
          return;
        }
        const allResponse = await fetch('/api/notifications/all');
        if (!allResponse.ok) throw new Error('Falha ao carregar todas as notificações');
        const allData = await allResponse.json();
        const allItems = Array.isArray(allData.items) ? allData.items : [];
        renderLists(allItems, { critical: criticalBox, important: importantBox, info: infoBox });
        infoBox.classList.remove('hidden');
        expand.textContent = 'OCULTAR INFORMATIVAS';
      };
    }
    return data;
  }

  window.ControladorNotifications = Object.freeze({ refresh: refreshNotifications });
})();
