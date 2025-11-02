// JavaScript to handle the Date Range filter
document.addEventListener('DOMContentLoaded', function() {
    const dateFilter = document.getElementById('date-filter');
    const customDateContainer = document.getElementById('custom-date-container');
    
    dateFilter.addEventListener('change', function() {
        if (this.value === 'custom') {
            customDateContainer.classList.remove('hidden');
        } else {
            customDateContainer.classList.add('hidden');
        }
    });
    
    // Export dropdown toggle
    const exportBtn = document.getElementById('exportBtn');
    const exportOptions = document.getElementById('exportOptions');
    const exportOptionButtons = document.querySelectorAll('#exportOptions .export-option');
    const filtersForm = document.getElementById('filters-form');
    
    exportBtn.addEventListener('click', function() {
        exportOptions.classList.toggle('hidden');
    });
    
    // Close export dropdown when clicking elsewhere
    document.addEventListener('click', function(event) {
        if (!exportBtn.contains(event.target)) {
            exportOptions.classList.add('hidden');
        }
    });
    // Handle export option clicks: fetch the file and trigger a client-side download reliably
    exportOptionButtons.forEach(btn => {
        btn.addEventListener('click', async function() {
            const format = this.getAttribute('data-format');
            const params = new URLSearchParams();
            if (filtersForm) {
                const formData = new FormData(filtersForm);
                for (const [k, v] of formData.entries()) {
                    if (v !== null && v !== '') params.append(k, v);
                }
            }
            params.set('format', format);
            const url = `/admin/inquiry/export?${params.toString()}`;
            try {
                const res = await fetch(url, { method: 'GET', credentials: 'same-origin' });
                if (!res.ok) {
                    let msg = 'Export failed';
                    try { const err = await res.json(); if (err && err.error) msg = err.error; } catch(_){}
                    alert(msg);
                    return;
                }
                const blob = await res.blob();
                let filename = '';
                const cd = res.headers.get('Content-Disposition') || res.headers.get('content-disposition');
                if (cd) {
                    const match = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(cd);
                    if (match) filename = decodeURIComponent(match[1] || match[2] || '').trim();
                }
                if (!filename) {
                    const ts = new Date().toISOString().slice(0,19).replace(/[:T]/g,'-');
                    const ext = format === 'pdf' ? 'pdf' : (format === 'excel' ? 'xlsx' : 'csv');
                    filename = `inquiries_${ts}.${ext}`;
                }
                const dlUrl = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = dlUrl;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(dlUrl);
                exportOptions.classList.add('hidden');
            } catch (e) {
                alert('Export failed');
            }
        });
    });
    
    // Modal handling for view details
    const modalButtons = document.querySelectorAll('.text-blue-600[title="View Details"]');
    const inquiryDetailModal = document.getElementById('inquiryDetailModal');
    const modalCloseButtons = document.querySelectorAll('.modal-close');
    const modalContent = document.getElementById('modal-content');
    
    modalButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            inquiryDetailModal.classList.remove('hidden');
            
            // Fetch inquiry details
            fetch(button.getAttribute('href'))
                .then(response => response.text())
                .then(data => {
                    modalContent.innerHTML = data;
                })
                .catch(error => {
                    modalContent.innerHTML = '<div class="text-center py-10 text-red-500">Error loading inquiry details.</div>';
                });
        });
    });
    
    modalCloseButtons.forEach(button => {
        button.addEventListener('click', function() {
            inquiryDetailModal.classList.add('hidden');
            modalContent.innerHTML = '<div class="flex justify-center items-center py-10"><div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-800"></div></div>';
        });
    });
    
    // Refresh button functionality
    document.getElementById('refreshBtn').addEventListener('click', function() {
        window.location.reload();
    });
});