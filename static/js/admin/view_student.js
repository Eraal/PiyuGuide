// Function to toggle student active status
function toggleStudentStatus(studentId, newStatus) {
    if (!confirm('Are you sure you want to ' + (newStatus ? 'activate' : 'deactivate') + ' this student account?')) {
        return;
    }

    const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    
    fetch('/admin/toggle_student_status', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({
            student_id: studentId,
            is_active: newStatus
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            window.location.reload(); // Refresh the page to reflect the new status
        } else {
            console.error('Error toggling student status:', data.message);
        }
    })
    .catch(error => {
        console.error('Unexpected error:', error);
    });
}

// Verify student email from view page
document.addEventListener('DOMContentLoaded', function(){
    const btn = document.getElementById('verify-email-btn');
    if (!btn) return;
    btn.addEventListener('click', async function(){
        const studentId = btn.getAttribute('data-student-id');
        if (!studentId) return;
        const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
        try {
            btn.disabled = true;
            btn.classList.add('opacity-60','cursor-not-allowed');
            const resp = await fetch('/admin/verify_student_email', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({ student_id: parseInt(studentId,10) })
            });
            if (!resp.ok) {
                const text = await resp.text();
                throw new Error(text || `Request failed (${resp.status})`);
            }
            const data = await resp.json();
            if (!data.success) throw new Error(data.message || 'Operation failed');
            // Reload to reflect updated status badges
            window.location.reload();
        } catch (err) {
            console.error(err);
            alert('Failed to verify email: ' + (err.message || err));
            btn.disabled = false;
            btn.classList.remove('opacity-60','cursor-not-allowed');
        }
    });
});
