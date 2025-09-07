// Unified Notification & Toast Utility
// Provides dropdown toggling, badge management, real-time prepend, and toast feedback.
// Usage: initNotifications({
//   role: 'super_admin',
//   ids: { bell:'sa-ann-bell', badge:'sa-ann-badge', dropdown:'sa-ann-dropdown', list:'sa-ann-list', markAll:'sa-ann-mark-all', refresh:'sa-ann-refresh' },
//   endpoints: { markAll:'/super-admin/notifications/mark-all-read', list:'/super-admin/notifications/recent' },
//   palette: { base:'#3b82f6', baseAlt:'#1e40af', success:'#10b981', warning:'#f59e0b', error:'#ef4444' }
// });

export function initNotifications(config) {
  const ids = config.ids || {};
  const el = id => document.getElementById(ids[id]);
  const bell = el('bell');
  const dropdown = el('dropdown');
  const list = el('list');
  const badge = el('badge');
  const markAllBtn = el('markAll');
  const refreshBtn = el('refresh');
  const endpoints = config.endpoints || {};
  const palette = Object.assign({ base:'#3b82f6', baseAlt:'#1e40af', success:'#10b981', warning:'#f59e0b', error:'#ef4444' }, config.palette || {});

  // Dropdown toggle with animation states
  if (bell && dropdown) {
    const openDropdown = () => {
      dropdown.classList.remove('hidden', 'closing');
      dropdown.classList.add('open');
      bell.setAttribute('aria-expanded', 'true');
      dropdown.setAttribute('aria-hidden', 'false');
    };
    const closeDropdown = () => {
      dropdown.classList.add('closing');
      bell.setAttribute('aria-expanded', 'false');
      dropdown.setAttribute('aria-hidden', 'true');
      setTimeout(() => {
        dropdown.classList.remove('open', 'closing');
        dropdown.classList.add('hidden');
      }, 180);
    };

    bell.addEventListener('click', (e) => {
      e.stopPropagation();
      const isOpen = dropdown.classList.contains('open') && !dropdown.classList.contains('hidden');
      if (isOpen) closeDropdown(); else openDropdown();
    });

    document.addEventListener('click', e => {
      if (!dropdown.contains(e.target) && !bell.contains(e.target)) {
        if (dropdown.classList.contains('open') && !dropdown.classList.contains('hidden')) {
          closeDropdown();
        }
      }
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && dropdown.classList.contains('open') && !dropdown.classList.contains('hidden')) {
        closeDropdown();
      }
    });
  }

  function updateBadge(delta=1) {
    if (!badge) return;
    let v = parseInt(badge.textContent || '0', 10) + delta;
    if (v < 0) v = 0;
    badge.textContent = String(v);
    if (v === 0) badge.classList.add('hidden'); else badge.classList.remove('hidden');
  }

  function createItem(n) {
    const a = document.createElement('a');
    a.href = n.link || '#';
    a.dataset.id = n.id || '';
    a.className = `sa-ann-item relative px-4 py-3 transition-colors ${n.is_read ? '' : 'unread'}`;
    const type = n.type || 'info';
    a.innerHTML = `
      <div class="icon-pill ${type}"><i class="${iconFor(type)}"></i></div>
      <div class="ann-body">
        <div class="ann-title">${escapeHtml(n.title || 'Notification')}</div>
        <div class="ann-msg line-clamp-2">${escapeHtml(n.message || '')}</div>
        <div class="ann-meta"><i class="fas fa-clock"></i>${formatTime(n.created_at)}</div>
      </div>`;
    return a;
  }

  function iconFor(type) {
    switch(type) {
      case 'success': return 'fas fa-check-circle';
      case 'warning': return 'fas fa-exclamation-triangle';
      case 'error': return 'fas fa-times-circle';
      default: return 'fas fa-bell';
    }
  }

  function formatTime(ts) {
    if (!ts) return new Date().toLocaleString();
    try { return new Date(ts).toLocaleString(undefined,{ month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' }); } catch { return ts; }
  }

  function escapeHtml(str) {
    return (str||'').replace(/[&<>"]/g, c=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[c]));
  }

  function ensureNotEmptyStateRemoved() {
    const empty = list ? list.querySelector('.sa-ann-empty') : null;
    if (empty) empty.remove();
  }

  function prepend(n) {
    if (!list) return;
    ensureNotEmptyStateRemoved();
    const item = createItem(n);
    list.prepend(item);
  }

  async function markAllRead() {
    if (!endpoints.markAll) return;
    try {
      const res = await fetch(endpoints.markAll, { method:'POST', headers:{ 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content }});
      if (res.ok) {
        if (list) list.querySelectorAll('.unread').forEach(el=>el.classList.remove('unread'));
        if (badge) { badge.textContent = '0'; badge.classList.add('hidden'); }
        showToast('All notifications marked as read','success');
      } else throw new Error('Failed');
    } catch { showToast('Could not mark all as read','error'); }
  }

  async function refreshList() {
    if (!endpoints.list) return;
    try {
      const res = await fetch(endpoints.list, { headers:{ 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content }});
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.notifications) && list) {
          list.innerHTML = '';
          data.notifications.forEach(n => list.appendChild(createItem(n)));
          if (data.unread_count !== undefined && badge) {
            badge.textContent = data.unread_count;
            if (data.unread_count>0) badge.classList.remove('hidden'); else badge.classList.add('hidden');
          }
          showToast('Notifications refreshed','success',1500);
        }
      }
    } catch { showToast('Refresh failed','error'); }
  }

  if (markAllBtn) markAllBtn.addEventListener('click', markAllRead);
  if (refreshBtn) refreshBtn.addEventListener('click', refreshList);

  // Toast system
  const toastZoneId = 'toast-zone';
  function getZone() {
    let z = document.getElementById(toastZoneId);
    if (!z) { z = document.createElement('div'); z.id = toastZoneId; z.className='toast-zone'; document.body.appendChild(z); }
    return z;
  }

  function showToast(message, type='info', duration=4000) {
    const zone = getZone();
    const t = document.createElement('div');
    t.className = `toast type-${type}`;
    t.setAttribute('role','alert');
    const iconMap = { info:'fas fa-bell', success:'fas fa-check', warning:'fas fa-exclamation', error:'fas fa-times' };
    t.innerHTML = `
      <div class="toast-icon-wrapper" style="background:linear-gradient(135deg,${palette[type]||palette.base},${palette.baseAlt})"><i class="${iconMap[type]||iconMap.info}"></i></div>
      <div class="toast-content"><div class="toast-title">${escapeHtml(capitalize(type))}</div><div class="toast-message">${escapeHtml(message)}</div></div>
      <button class="toast-close" aria-label="Close"><i class="fas fa-times"></i></button>
      <div class="progress-bar"><div class="progress-fill" style="animation-duration:${duration}ms"></div></div>`;
    zone.appendChild(t);
    const close = () => { t.classList.add('closing'); setTimeout(()=> t.remove(), 320); };
    t.querySelector('.toast-close').addEventListener('click', close);
    setTimeout(close, duration);
  }

  function capitalize(s){ return s.charAt(0).toUpperCase()+s.slice(1); }

  // Public API additions
  return {
    addRealtime(notification) {
      prepend(notification);
      updateBadge(1);
      showToast(notification.toast_message || notification.message || 'New notification');
    },
    showToast,
    updateBadge
  };
}
