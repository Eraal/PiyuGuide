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
    tr.className = "inquiry-row hover:bg-gradient-to-r hover:from-blue-50 hover:to-green-50 transition-all duration-200 border-l-4 border-l-yellow-400 bg-yellow-50/30";
    tr.dataset.inquiryId = data.id;
    const createdAt = new Date(data.created_at);
    const dateStr = createdAt.toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'});
    tr.innerHTML = rowHtml(data, dateStr);
    tbody.insertBefore(tr, tbody.firstChild);
  }

  function rowHtml(data, dateStr){
    const subj = escapeHtml(data.subject || '');
    const studentName = escapeHtml(data.student_name || 'Student');
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
            <i class="fas fa-user text-gray-600"></i>
          </div>
          <div>
            <div class="font-medium text-gray-800 max-w-[140px] truncate" title="${studentName}">${studentName}</div>
            <div class="text-xs text-gray-500">New</div>
          </div>
        </div>
      </td>
      <td class="py-5 px-6"><span class="text-xs text-gray-400">—</span></td>
      <td class="py-5 px-6 text-sm text-gray-600">${dateStr}</td>
      <td class="py-5 px-6">
        <span class="status-pill px-3 py-1 rounded-full text-xs font-semibold bg-yellow-100 text-yellow-700" data-status="pending">Pending</span>
      </td>
      <td class="py-5 px-6">
        <a href="/office/inquiry/${data.id}" class="inline-flex items-center px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium shadow-sm transition-colors">
          <i class="fas fa-eye mr-1"></i> View
        </a>
      </td>`;
  }

  function updateRowStatus(row, newStatus){
    const pill = row.querySelector('.status-pill');
    if(pill){
      pill.dataset.status = newStatus;
      pill.textContent = titleCase(newStatus.replace('_',' '));
      // Reset classes
      pill.className = 'status-pill px-3 py-1 rounded-full text-xs font-semibold';
      if(newStatus === 'pending') pill.classList.add('bg-yellow-100','text-yellow-700');
      else if(newStatus === 'in_progress') pill.classList.add('bg-blue-100','text-blue-700');
      else if(newStatus === 'resolved') pill.classList.add('bg-green-100','text-green-700');
      else pill.classList.add('bg-gray-100','text-gray-700');
    }
    // Update border color class on row
    row.className = row.className.replace(/border-l-(yellow|blue|green|gray)-400[^ ]*/g,'');
    if(newStatus === 'pending') row.classList.add('border-l-yellow-400','bg-yellow-50/30');
    else if(newStatus === 'in_progress') row.classList.add('border-l-blue-400','bg-blue-50/30');
    else if(newStatus === 'resolved') row.classList.add('border-l-green-400','bg-green-50/30');
    else row.classList.add('border-l-gray-400');
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

  // Public init
  function initOfficeInquiryRealtime(){ ensureSocket(); }

  global.initOfficeInquiryRealtime = initOfficeInquiryRealtime;

  document.addEventListener('DOMContentLoaded', initOfficeInquiryRealtime);
})(window);
