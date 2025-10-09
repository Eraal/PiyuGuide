// Real-time utilities for office inquiries page
// Handles: new inquiry insertion (with page 1 guard), status change updates, badge/stat sync

(function(global){
  const state = {
    socket: null,
    page: 1,
    initialized: false,
    lastSeenInquiryId: null,
    pollIntervalId: null,
    connected: false
  };

  // Determine page reliably
  try {
    const html = document.documentElement;
    const attrPage = html.getAttribute('data-current-page');
    if(attrPage) state.page = parseInt(attrPage,10) || 1; else state.page = 1;
  } catch(e){ state.page = 1; }

  function ensureSocket(){
    if(state.socket) return state.socket;
    try {
      state.socket = io('/office', { transports:['websocket','polling'] });
      state.socket.on('connect', () => {
        state.connected = true;
        // stop fallback polling if any
        if(state.pollIntervalId){ clearInterval(state.pollIntervalId); state.pollIntervalId = null; }
        console.debug('[InquiriesRealtime] Connected to /office');
      });
      state.socket.on('disconnect', () => {
        state.connected = false;
        console.warn('[InquiriesRealtime] Disconnected. Activating fallback polling.');
        startFallbackPolling();
      });
      bindSocketEvents(state.socket);
    } catch(e){ console.warn('Socket init failed', e); startFallbackPolling(); }
    return state.socket;
  }

  function bindSocketEvents(socket){
    if(state.initialized) return; // avoid duplicate
    state.initialized = true;

    socket.on('new_office_inquiry', handleNewInquiry);
    socket.on('inquiry_status_changed', handleStatusChange);
  }

  function handleNewInquiry(data){
    if(!data || !data.id) return;
    // Duplicate guard
    if(document.querySelector(`tr[data-inquiry-id="${data.id}"]`)) return;
    if(state.page !== 1){
      showNewInquiryBanner(data);
      incrementPendingBadge();
      incrementPendingStat();
      return;
    }
    insertInquiryRow(data);
    incrementPendingBadge();
    incrementPendingStat();
    toast('New Inquiry', `${data.student_name || 'Student'}: ${escapeHtml(data.subject)}`,'success');
  }

  function handleStatusChange(data){
    if(!data || !data.id) return;
    const { id, old_status, new_status } = data;
    // Adjust pending badge if moving away from pending
    if(old_status === 'pending' && new_status !== 'pending'){
      decrementPendingBadge();
      decrementPendingStat();
    } else if(old_status !== 'pending' && new_status === 'pending') {
      incrementPendingBadge();
      incrementPendingStat();
    }

    // Update row style & status pill if present on current page
    const row = document.querySelector(`tr[data-inquiry-id="${id}"]`);
    if(row){
      updateRowStatus(row, new_status);
    }
  }

  function insertInquiryRow(data){
    const tbody = document.getElementById('inquiryTable');
    if(!tbody) return;
    // Track max ID
    try { state.lastSeenInquiryId = Math.max(state.lastSeenInquiryId || 0, data.id); } catch(_) {}
  const tr = document.createElement('tr');
  // Mirror template row classes and attributes; compute status color
  const s0 = (data.status || 'pending').toLowerCase();
  let statusRowCls = 'border-l-gray-400';
  if(s0 === 'pending') statusRowCls = 'border-l-yellow-400 bg-yellow-50/30';
  else if(s0 === 'in_progress') statusRowCls = 'border-l-blue-400 bg-blue-50/30';
  else if(s0 === 'resolved') statusRowCls = 'border-l-green-400 bg-green-50/30';
  tr.className = `inquiry-row cursor-pointer hover:bg-gradient-to-r hover:from-blue-50 hover:to-green-50 transition-all duration-200 border-l-4 ${statusRowCls}`;
    tr.dataset.inquiryId = data.id;
    tr.setAttribute('data-detail-url', `/office/inquiry/${data.id}`);
    tr.setAttribute('tabindex', '0');
    tr.setAttribute('aria-label', `Open inquiry ${data.id} details`);

    const createdAt = data.created_at ? new Date(data.created_at) : new Date();
    const dateStr = createdAt.toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'});
    tr.innerHTML = rowHtml(data, dateStr);
    tbody.insertBefore(tr, tbody.firstChild);

    // Attach interactions to match template behavior
    bindRowInteractions(tr);
    bindActionButtons(tr);
  }

  function rowHtml(data, dateStr){
    const subj = escapeHtml(data.subject || '');
    const studentName = escapeHtml(data.student_name || 'Student');
    const initials = (studentName || '').trim().split(/\s+/).map(w => w[0]).slice(0,2).join('').toUpperCase() || 'ST';

    // Build status badge like the template
    const status = (data.status || 'pending').toLowerCase();
    let statusBadge = '';
    if(status === 'pending'){
      statusBadge = `<span class="inline-flex items-center px-3 py-2 rounded-full text-xs font-bold shadow-md bg-gradient-to-r from-yellow-400 to-yellow-500 text-yellow-900 animate-pulse"><i class="fas fa-clock mr-1"></i>Pending</span>`;
    } else if(status === 'in_progress'){
      statusBadge = `<span class="inline-flex items-center px-3 py-2 rounded-full text-xs font-bold shadow-md bg-gradient-to-r from-blue-400 to-blue-500 text-blue-900"><i class="fas fa-spinner mr-1"></i>In Progress</span>`;
    } else if(status === 'resolved'){
      statusBadge = `<span class="inline-flex items-center px-3 py-2 rounded-full text-xs font-bold shadow-md bg-gradient-to-r from-green-400 to-green-500 text-green-900"><i class="fas fa-check-circle mr-1"></i>Resolved</span>`;
    } else {
      const label = titleCase(status.replace('_',' '));
      statusBadge = `<span class="inline-flex items-center px-3 py-2 rounded-full text-xs font-bold shadow-md bg-gradient-to-r from-gray-400 to-gray-500 text-gray-900"><i class="fas fa-ban mr-1"></i>${escapeHtml(label)}</span>`;
    }

    // Build concern chips if provided
    let concernsHtml = '';
    try {
      const concerns = Array.isArray(data.concerns) ? data.concerns : [];
      if(concerns.length){
        concernsHtml = concerns.map(c => {
          const nm = escapeHtml(c.name || 'Concern');
          const other = c.other_specification ? `<span class="text-gray-600 ml-1">(${escapeHtml(c.other_specification)})</span>` : '';
          const cid = c.id != null ? ` data-concern-id="${c.id}"` : '';
          return `<span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-gradient-to-r from-gray-100 to-gray-200 text-gray-800 border border-gray-300 shadow-sm"${cid}><i class="fas fa-tag mr-1 text-gray-500"></i>${nm}${other}</span>`;
        }).join('');
      } else {
        concernsHtml = '<span class="text-xs text-gray-400">—</span>';
      }
    } catch(_) {
      concernsHtml = '<span class="text-xs text-gray-400">—</span>';
    }

    return `
      <td class="py-5 px-6 whitespace-nowrap">
        <div class="flex items-center">
          <div class="w-8 h-8 bg-gradient-to-br from-gray-500 to-gray-600 rounded-lg flex items-center justify-center text-white font-bold text-sm shadow-md">${data.id}</div>
        </div>
      </td>
      <td class="py-5 px-6">
        <div class="flex items-center space-x-3">
          <a href="/office/inquiry/${data.id}" class="text-blue-600 hover:text-blue-800 font-medium hover:underline transition-colors duration-200 max-w-xs truncate" title="${subj}">${subj}</a>
        </div>
      </td>
      <td class="py-5 px-6">
        <div class="flex items-center space-x-3">
          <div class="w-10 h-10 rounded-full bg-gradient-to-br from-gray-300 to-gray-400 flex items-center justify-center shadow-md">
            <span class="text-white font-semibold text-sm">${initials}</span>
          </div>
          <div>
            <div class="text-sm font-medium text-gray-900">${studentName}</div>
            <div class="text-xs text-gray-500">Student</div>
          </div>
        </div>
      </td>
      <td class="py-5 px-6">
        <div class="flex flex-wrap gap-2">${concernsHtml}</div>
      </td>
      <td class="py-5 px-6 whitespace-nowrap">
        <div class="flex items-center space-x-2">
          <i class="fas fa-calendar-alt text-gray-400"></i>
          <span class="text-sm text-gray-900 font-medium">${dateStr}</span>
        </div>
      </td>
      <td class="py-5 px-6 whitespace-nowrap">
        ${statusBadge}
      </td>
      <td class="py-5 px-6 whitespace-nowrap">
        <div class="flex items-center space-x-3">
          <a href="/office/inquiry/${data.id}" class="w-9 h-9 bg-blue-100 hover:bg-blue-200 rounded-lg flex items-center justify-center text-blue-600 hover:text-blue-800 transition-all duration-200 hover:scale-110 shadow-md hover:shadow-lg" title="View Details">
            <i class="fas fa-eye"></i>
          </a>
          <a href="#" class="w-9 h-9 bg-green-100 hover:bg-green-200 rounded-lg flex items-center justify-center text-green-600 hover:text-green-800 transition-all duration-200 hover:scale-110 shadow-md hover:shadow-lg updateStatusBtn" data-inquiry-id="${data.id}" title="Update Status">
            <i class="fas fa-edit"></i>
          </a>
          <a href="#" class="w-9 h-9 bg-red-100 hover:bg-red-200 rounded-lg flex items-center justify-center text-red-600 hover:text-red-800 transition-all duration-200 hover:scale-110 shadow-md hover:shadow-lg deleteInquiryBtn" data-inquiry-id="${data.id}" data-status="${escapeHtml(status)}" title="Delete">
            <i class="fas fa-trash"></i>
          </a>
        </div>
      </td>`;
  }

  function updateRowStatus(row, newStatus){
    // Update status badge like template (6th td span)
    const statusCellSpan = row.querySelector('td:nth-child(6) span');
    if(statusCellSpan){
      let iconHtml = '';
      let cls = 'inline-flex items-center px-3 py-2 rounded-full text-xs font-bold shadow-md ';
      const s = (newStatus || '').toLowerCase();
      let label = titleCase((s || 'pending').replace('_',' '));
      if(s === 'pending'){
        iconHtml = '<i class="fas fa-clock mr-1"></i>';
        cls += 'bg-gradient-to-r from-yellow-400 to-yellow-500 text-yellow-900 animate-pulse';
      } else if(s === 'in_progress'){
        iconHtml = '<i class="fas fa-spinner mr-1"></i>';
        cls += 'bg-gradient-to-r from-blue-400 to-blue-500 text-blue-900';
      } else if(s === 'resolved'){
        iconHtml = '<i class="fas fa-check-circle mr-1"></i>';
        cls += 'bg-gradient-to-r from-green-400 to-green-500 text-green-900';
      } else {
        iconHtml = '<i class="fas fa-ban mr-1"></i>';
        cls += 'bg-gradient-to-r from-gray-400 to-gray-500 text-gray-900';
      }
      statusCellSpan.className = cls;
      statusCellSpan.innerHTML = iconHtml + label;
    }
    // Update border & bg color class on row (match template)
    row.className = row.className
      .replace(/border-l-(yellow|blue|green|gray)-400/g, '')
      .replace(/bg-(yellow|blue|green|gray)-50\/30/g, '')
      .trim();
    if(newStatus === 'pending'){
      row.classList.add('border-l-yellow-400','bg-yellow-50/30');
    } else if(newStatus === 'in_progress'){
      row.classList.add('border-l-blue-400','bg-blue-50/30');
    } else if(newStatus === 'resolved'){
      row.classList.add('border-l-green-400','bg-green-50/30');
    } else {
      row.classList.add('border-l-gray-400');
    }
    // Keep delete button data-status in sync
    const delBtn = row.querySelector('.deleteInquiryBtn');
    if(delBtn){ delBtn.setAttribute('data-status', (newStatus || '').toLowerCase()); }
  }

  function showNewInquiryBanner(data){
    const existing = document.getElementById('new-inquiry-banner');
    if(existing){ existing.remove(); }
    const banner = document.createElement('div');
    banner.id = 'new-inquiry-banner';
    banner.className = 'mb-4 p-4 rounded-lg bg-blue-50 border border-blue-200 text-blue-800 flex items-center justify-between shadow-sm';
    banner.innerHTML = `<div class="flex items-center space-x-2"><i class="fas fa-bell"></i><span>New inquiry (#${data.id}) received: ${escapeHtml(data.subject || '')}</span></div><div class="flex items-center space-x-2"><button class="px-3 py-1.5 text-xs font-semibold bg-blue-600 text-white rounded-md hover:bg-blue-700" id="reloadForInquiry">Reload</button><button class="px-3 py-1.5 text-xs font-semibold bg-white text-blue-700 border border-blue-300 rounded-md hover:bg-blue-100" id="dismissInquiryBanner">Dismiss</button></div>`;
    const container = document.getElementById('inquiries-page-root') || document.body;
    container.insertBefore(banner, container.firstChild);
    banner.querySelector('#reloadForInquiry').addEventListener('click', ()=> window.location.reload());
    banner.querySelector('#dismissInquiryBanner').addEventListener('click', ()=> banner.remove());
  }

  function incrementPendingBadge(){ modifyPendingBadge(1); }
  function decrementPendingBadge(){ modifyPendingBadge(-1); }
  function modifyPendingBadge(delta){
    const link = document.getElementById('nav-inquiries');
    if(!link) return;
    let badge = link.querySelector('.counter-badge.counter-red');
    if(!badge && delta > 0){
      badge = document.createElement('span');
      badge.className = 'ml-auto counter-badge counter-red';
      badge.textContent = '0';
      link.appendChild(badge);
    }
    if(!badge) return;
    let val = parseInt(badge.textContent.trim(),10) || 0;
    val = Math.max(0, val + delta);
    badge.textContent = val;
    if(val === 0) badge.remove();
  }

  function incrementPendingStat(){ modifyPendingStat(1); }
  function decrementPendingStat(){ modifyPendingStat(-1); }
  function modifyPendingStat(delta){
    // Find the pending stat card and bump its numeric value
    const statBlocks = document.querySelectorAll('.stats-card');
    statBlocks.forEach(card => {
      // Locate a label element whose text contains 'Pending'
      const labelEl = Array.from(card.querySelectorAll('h1,h2,h3,h4,h5,h6,p,span,strong'))
        .find(el => /pending/i.test((el.textContent||'').trim()));
      if(!labelEl) return;
      // Value element in this layout is the big number (p.text-2xl ...)
      let valueEl = card.querySelector('p.text-2xl');
      if(!valueEl){
        // Fallback: find the first element with a numeric content
        valueEl = Array.from(card.querySelectorAll('p,span,div')).find(el => /\d+/.test((el.textContent||'').trim()));
      }
      if(!valueEl) return;
      let val = parseInt((valueEl.textContent||'0').replace(/[^0-9]/g,''),10) || 0;
      val = Math.max(0, val + delta);
      valueEl.textContent = String(val);
    });
  }

  function toast(title, msg, type){
    if(global.showNotification){
      global.showNotification(title, msg, type || 'info', 6000);
    }
  }

  function startFallbackPolling(){
    if(state.pollIntervalId) return;
    // Set baseline lastSeenInquiryId
    if(state.lastSeenInquiryId == null){
      const firstRow = document.querySelector('#inquiryTable tr[data-inquiry-id]');
      if(firstRow){ state.lastSeenInquiryId = parseInt(firstRow.getAttribute('data-inquiry-id'),10) || null; }
    }
    state.pollIntervalId = setInterval(() => {
      if(state.connected) return;
      fetch('/office/api/inquiries/latest?after_id=' + (state.lastSeenInquiryId || 0))
        .then(r => r.ok ? r.json() : null)
        .then(data => {
          if(!data || !Array.isArray(data.items)) return;
            data.items.forEach(item => handleNewInquiry(item));
        })
        .catch(()=>{});
    }, 8000);
  }

  function escapeHtml(str){
    return String(str==null? '': str)
      .replace(/&/g,'&amp;')
      .replace(/</g,'&lt;')
      .replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;')
      .replace(/'/g,'&#39;');
  }
  function titleCase(s){ return s.split(' ').map(w => w.charAt(0).toUpperCase()+w.slice(1)).join(' '); }

  // Match template row behaviors for newly inserted rows
  function bindRowInteractions(row){
    // Hover micro-animation
    row.addEventListener('mouseenter', function(){
      this.style.transform = 'scale(1.01)';
      this.style.transition = 'transform 0.2s ease-in-out';
    });
    row.addEventListener('mouseleave', function(){
      this.style.transform = 'scale(1)';
    });
    // Click navigation, ignore inner interactive elements
    row.addEventListener('click', function(e){
      const target = e.target;
      if(target.closest('a, button, .updateStatusBtn, .deleteInquiryBtn, [role="button"]')) return;
      const url = row.getAttribute('data-detail-url');
      if(url){ window.location.href = url; }
    });
    // Keyboard accessibility
    row.addEventListener('keydown', function(e){
      if(e.key === 'Enter' || e.key === ' '){
        const active = document.activeElement;
        if(active && active.closest('a, button, .updateStatusBtn, .deleteInquiryBtn, [role="button"]')) return;
        e.preventDefault();
        const url = row.getAttribute('data-detail-url');
        if(url){ window.location.href = url; }
      }
    });
  }

  // Bind action buttons (status update & delete) to existing modals on the page
  function bindActionButtons(scope){
    const statusBtn = scope.querySelector('.updateStatusBtn');
    if(statusBtn){
      statusBtn.addEventListener('click', function(e){
        e.preventDefault();
        const inquiryId = this.getAttribute('data-inquiry-id');
        const statusUpdateModal = document.getElementById('statusUpdateModal');
        const inquiryIdInput = document.getElementById('inquiryId');
        if(inquiryIdInput) inquiryIdInput.value = inquiryId;
        if(statusUpdateModal){ statusUpdateModal.classList.remove('hidden'); }
      });
    }
    const deleteBtn = scope.querySelector('.deleteInquiryBtn');
    if(deleteBtn){
      deleteBtn.addEventListener('click', function(e){
        e.preventDefault();
        const inquiryId = this.getAttribute('data-inquiry-id');
        const status = (this.getAttribute('data-status') || '').toLowerCase();
        const deleteConfirmModal = document.getElementById('deleteConfirmModal');
        const deleteInquiryIdInput = document.getElementById('deleteInquiryId');
        const statusWarning = document.getElementById('statusWarning');
        if(deleteInquiryIdInput) deleteInquiryIdInput.value = inquiryId;
        if(statusWarning){
          let msg = '';
          if (status === 'pending') {
            msg = 'This inquiry is still Pending. Deleting it now will permanently remove an active case.';
          } else if (status === 'in_progress') {
            msg = 'This inquiry is In Progress. Deleting it will terminate an ongoing conversation.';
          } else if (status === 'resolved') {
            msg = 'This inquiry is Resolved. Consider closing instead if you want to keep records.';
          } else { msg = ''; }
          if(msg){ statusWarning.textContent = msg; statusWarning.classList.remove('hidden'); }
          else { statusWarning.classList.add('hidden'); }
        }
        if(deleteConfirmModal){ deleteConfirmModal.classList.remove('hidden'); }
      });
    }
  }

  // Public init
  function initOfficeInquiryRealtime(){ ensureSocket(); }

  global.initOfficeInquiryRealtime = initOfficeInquiryRealtime;

  document.addEventListener('DOMContentLoaded', initOfficeInquiryRealtime);
})(window);
