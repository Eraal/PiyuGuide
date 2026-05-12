/**
 * Office Notifications JavaScript
 * Handles functionality for the office notifications page
 */

class OfficeNotificationsManager {
    constructor() {
        this.csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        this.modal = new NotificationsModalController();
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.setupAutoRefresh();
    }

    setupEventListeners() {
        // Mark all as read button
        const markAllReadBtn = document.getElementById('markAllReadBtn');
        if (markAllReadBtn) {
            markAllReadBtn.addEventListener('click', () => this.markAllAsRead());
        }

        // Delete all read button
        const deleteAllReadBtn = document.getElementById('deleteAllReadBtn');
        if (deleteAllReadBtn) {
            deleteAllReadBtn.addEventListener('click', () => this.deleteAllRead());
        }

        // Filter change listeners
        document.getElementById('readFilter')?.addEventListener('change', this.applyFilters);
        document.getElementById('typeFilter')?.addEventListener('change', this.applyFilters);

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey || e.metaKey) {
                switch (e.key) {
                    case 'a':
                        e.preventDefault();
                        this.markAllAsRead();
                        break;
                    case 'r':
                        e.preventDefault();
                        window.location.reload();
                        break;
                }
            }
        });

        // Delegate clicks for action buttons
        document.getElementById('notificationsContainer')?.addEventListener('click', (e) => {
            const btnMark = e.target.closest('.js-mark-read');
            if (btnMark) {
                const id = btnMark.getAttribute('data-id');
                if (id) this.markAsRead(id);
                return;
            }
            const btnDelete = e.target.closest('.js-delete');
            if (btnDelete) {
                const id = btnDelete.getAttribute('data-id');
                if (id) this.deleteNotification(id);
                return;
            }
        });
    }

    setupAutoRefresh() {
        // Auto-refresh page every 5 minutes to get new notifications
        setInterval(() => {
            this.checkForNewNotifications();
        }, 300000); // 5 minutes
    }

    async checkForNewNotifications() {
        try {
            const response = await fetch('/office/notifications/get-unread-count');
            const data = await response.json();
            
            // Update the page title if there are new notifications
            const currentCount = parseInt(document.title.match(/\((\d+)\)/) || [0, 0])[1];
            if (data.unread_count > currentCount) {
                document.title = `(${data.unread_count}) Notifications - KapiyuGuide Office`;
                // Avoid extra browser toasts on this page per UX: rely on the bell badge and dropdown
            }
        } catch (error) {
            console.error('Error checking for new notifications:', error);
        }
    }

    async markAsRead(notificationId) {
        try {
            // Show non-blocking inline progress within the modal area
            this.modal.showProgress('Marking notification as read...');
            const response = await fetch(`/office/notifications/mark-read/${notificationId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                }
            });

            const data = await response.json();
            
            if (data.success) {
                this.updateNotificationItem(notificationId, true);
                this.modal.showSuccess('Notification marked as read');
                setTimeout(() => window.location.reload(), 900);
            } else {
                this.modal.showError('Error marking notification as read');
            }
        } catch (error) {
            console.error('Error:', error);
            this.modal.showError('Error marking notification as read');
        }
    }

    async deleteNotification(notificationId) {
        try {
            const proceed = await this.modal.confirm('Are you sure you want to delete this notification? This action cannot be undone.', {confirmLabel: 'Delete', confirmTone: 'danger'});
            if (!proceed) return;
            this.modal.showProgress('Deleting notification...');
            const response = await fetch(`/office/notifications/delete/${notificationId}`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                }
            });

            const data = await response.json();
            
            if (data.success) {
                this.removeNotificationItem(notificationId);
                this.modal.showSuccess('Notification deleted');
                setTimeout(() => window.location.reload(), 900);
            } else {
                this.modal.showError('Error deleting notification');
            }
        } catch (error) {
            console.error('Error:', error);
            this.modal.showError('Error deleting notification');
        }
    }

    async markAllAsRead() {
        try {
            const proceed = await this.modal.confirm('Mark all notifications as read?', {confirmLabel: 'Mark All Read', confirmTone: 'primary'});
            if (!proceed) return;
            this.modal.showProgress('Marking all notifications as read...');
            const response = await fetch('/office/notifications/mark-all-read', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                }
            });

            const data = await response.json();
            
            if (data.success) {
                this.modal.showSuccess(data.message || 'All notifications marked as read');
                setTimeout(() => window.location.reload(), 900);
            } else {
                this.modal.showError('Error marking all notifications as read');
            }
        } catch (error) {
            console.error('Error:', error);
            this.modal.showError('Error marking all notifications as read');
        }
    }

    async deleteAllRead() {
        try {
            const proceed = await this.modal.confirm('Delete all read notifications? This cannot be undone.', {confirmLabel: 'Delete All Read', confirmTone: 'danger'});
            if (!proceed) return;
            this.modal.showProgress('Deleting read notifications...');
            const response = await fetch('/office/notifications/delete-all-read', {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                }
            });

            const data = await response.json();
            
            if (data.success) {
                this.modal.showSuccess(data.message || 'Read notifications cleared');
                setTimeout(() => window.location.reload(), 900);
            } else {
                this.modal.showError('Error deleting read notifications');
            }
        } catch (error) {
            console.error('Error:', error);
            this.modal.showError('Error deleting read notifications');
        }
    }

    updateNotificationItem(notificationId, isRead) {
        const item = document.querySelector(`[data-notification-id="${notificationId}"]`);
        if (item) {
            if (isRead) {
                item.classList.remove('bg-blue-50', 'border-l-4', 'border-blue-500');
                // Remove "New" badge and mark as read button
                const newBadge = item.querySelector('.bg-red-500');
                const markReadBtn = item.querySelector('button[onclick*="markAsRead"]');
                if (newBadge) newBadge.remove();
                if (markReadBtn) markReadBtn.remove();
            }
        }
    }

    removeNotificationItem(notificationId) {
        const item = document.querySelector(`[data-notification-id="${notificationId}"]`);
        if (item) {
            item.style.opacity = '0';
            setTimeout(() => item.remove(), 300);
        }
    }

    applyFilters() {
        const readFilter = document.getElementById('readFilter').value;
        const typeFilter = document.getElementById('typeFilter').value;
        
        const params = new URLSearchParams();
        if (readFilter) params.append('read', readFilter);
        if (typeFilter) params.append('type', typeFilter);
        
        window.location.href = `/office/notifications?${params.toString()}`;
    }

    clearFilters() {
        window.location.href = '/office/notifications';
    }

    // Intentionally no toast/browser notification on this page. Modal UX only.
}

// Global functions for onclick handlers
window.markAsRead = function(notificationId) {
    if (window.notificationsManager) {
        window.notificationsManager.markAsRead(notificationId);
    }
};

window.deleteNotification = function(notificationId) {
    if (window.notificationsManager) {
        window.notificationsManager.deleteNotification(notificationId);
    }
};

window.applyFilters = function() {
    if (window.notificationsManager) {
        window.notificationsManager.applyFilters();
    }
};

window.clearFilters = function() {
    if (window.notificationsManager) {
        window.notificationsManager.clearFilters();
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.notificationsManager = new OfficeNotificationsManager();
});

// Export for potential use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = OfficeNotificationsManager;
}

// Modal controller dedicated to notifications page
function NotificationsModalController() {
    this.modal = document.getElementById('confirmationModal');
    this.msgEl = document.getElementById('confirmationMessage');
    this.confirmBtn = document.getElementById('confirmActionBtn');
    this.cancelBtn = this.modal ? this.modal.querySelector('button:not(#confirmActionBtn)') : null;
}

NotificationsModalController.prototype._open = function() {
    if (!this.modal) return;
    this.modal.classList.remove('hidden');
};

NotificationsModalController.prototype._close = function() {
    if (!this.modal) return;
    this.modal.classList.add('hidden');
};

NotificationsModalController.prototype.confirm = function(message, {confirmLabel='Confirm', confirmTone='primary'} = {}) {
    return new Promise((resolve) => {
        if (!this.modal) { resolve(window.confirm(message)); return; }
        this._resetButtons();
        this.msgEl.textContent = message;
        this._styleConfirm(confirmTone);
        this.confirmBtn.textContent = confirmLabel;
        const onConfirm = () => { cleanup(); resolve(true); };
        const onCancel = () => { cleanup(); resolve(false); };
        const cleanup = () => {
            this.confirmBtn.removeEventListener('click', onConfirm);
            if (this.cancelBtn) this.cancelBtn.removeEventListener('click', onCancel);
            this._close();
        };
        this.confirmBtn.addEventListener('click', onConfirm);
        if (this.cancelBtn) this.cancelBtn.addEventListener('click', onCancel);
        this._open();
    });
};

NotificationsModalController.prototype.showProgress = function(message) {
    if (!this.modal) return;
    this._open();
    this.msgEl.innerHTML = `<div class="flex items-center gap-3"><span class="inline-block w-4 h-4 border-2 border-gray-300 border-t-blue-500 rounded-full animate-spin"></span><span>${message}</span></div>`;
    this._disableButtons(true);
    this._styleConfirm('neutral');
    this.confirmBtn.textContent = 'Please wait...';
};

NotificationsModalController.prototype.showSuccess = function(message) {
    if (!this.modal) return;
    this._open();
    this.msgEl.innerHTML = `<div class="flex items-center gap-3 text-green-700"><span class="w-6 h-6 rounded-full bg-green-100 flex items-center justify-center"><i class="fas fa-check text-green-600"></i></span><span>${message}</span></div>`;
    this._disableButtons(true);
    this._styleConfirm('success');
    this.confirmBtn.textContent = 'Done';
    setTimeout(() => this._close(), 800);
};

NotificationsModalController.prototype.showError = function(message) {
    if (!this.modal) return;
    this._open();
    this.msgEl.innerHTML = `<div class="flex items-center gap-3 text-red-700"><span class="w-6 h-6 rounded-full bg-red-100 flex items-center justify-center"><i class="fas fa-exclamation text-red-600"></i></span><span>${message}</span></div>`;
    this._disableButtons(false);
    this._styleConfirm('danger');
    this.confirmBtn.textContent = 'Close';
    // Make confirm act as close in error state
    const handler = () => { this.confirmBtn.removeEventListener('click', handler); this._close(); };
    this.confirmBtn.addEventListener('click', handler);
};

NotificationsModalController.prototype._disableButtons = function(disabled) {
    if (this.confirmBtn) this.confirmBtn.disabled = disabled;
    if (this.cancelBtn) this.cancelBtn.disabled = disabled;
};

NotificationsModalController.prototype._resetButtons = function() {
    this._disableButtons(false);
};

NotificationsModalController.prototype._styleConfirm = function(tone) {
    if (!this.confirmBtn) return;
    // Reset classes, then apply tone
    this.confirmBtn.className = 'px-4 py-2 rounded-lg text-white transition-colors';
    if (tone === 'danger') {
        this.confirmBtn.classList.add('bg-red-600','hover:bg-red-700');
    } else if (tone === 'success') {
        this.confirmBtn.classList.add('bg-green-600','hover:bg-green-700');
    } else if (tone === 'neutral') {
        this.confirmBtn.classList.add('bg-gray-400');
    } else { // primary
        this.confirmBtn.classList.add('bg-blue-600','hover:bg-blue-700');
    }
};
