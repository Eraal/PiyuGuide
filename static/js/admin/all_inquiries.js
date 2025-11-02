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
    // Handle export option clicks
    exportOptionButtons.forEach(btn => {
        btn.addEventListener('click', async function() {
            const format = this.getAttribute('data-format');
            // Build form data from current filters
            const fd = new FormData();
            if (filtersForm) {
                const formData = new FormData(filtersForm);
                for (const [k, v] of formData.entries()) {
                    if (v !== null && v !== '') fd.append(k, v);
                }
            }
            fd.append('format', format);

            try {
                const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
                const res = await fetch('/admin/inquiry/export', {
                    method: 'POST',
                    body: fd,
                    headers: csrf ? { 'X-CSRFToken': csrf } : undefined
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    alert(err.error || 'Export failed');
                    return;
                }
                const blob = await res.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                // Guess filename by content-type
                let ext = 'csv';
                const ct = res.headers.get('Content-Type') || '';
                if (ct.includes('pdf')) ext = 'pdf';
                else if (ct.includes('spreadsheet')) ext = 'xlsx';
                a.href = url;
                a.download = `inquiries_${new Date().toISOString().slice(0,19).replace(/[:T]/g,'-')}.${ext}`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(url);
                exportOptions.classList.add('hidden');
            } catch (e) {
                alert('Export failed');
            }
        })
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