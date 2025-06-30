/**
 * Office Notifications JavaScript
 * Handles functionality for the office notifications page
 */

class OfficeNotificationsManager {
    constructor() {
        this.csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
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
                this.showNotification('New notifications received', 'info');
            }
        } catch (error) {
            console.error('Error checking for new notifications:', error);
        }
    }

    async markAsRead(notificationId) {
        try {
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
                this.showNotification('Notification marked as read', 'success');
                setTimeout(() => window.location.reload(), 1000);
            } else {
                this.showNotification('Error marking notification as read', 'error');
            }
        } catch (error) {
            console.error('Error:', error);
            this.showNotification('Error marking notification as read', 'error');
        }
    }

    async deleteNotification(notificationId) {
        if (!confirm('Are you sure you want to delete this notification?')) {
            return;
        }

        try {
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
                this.showNotification('Notification deleted successfully', 'success');
                setTimeout(() => window.location.reload(), 1000);
            } else {
                this.showNotification('Error deleting notification', 'error');
            }
        } catch (error) {
            console.error('Error:', error);
            this.showNotification('Error deleting notification', 'error');
        }
    }

    async markAllAsRead() {
        if (!confirm('Are you sure you want to mark all notifications as read?')) {
            return;
        }

        try {
            const response = await fetch('/office/notifications/mark-all-read', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                }
            });

            const data = await response.json();
            
            if (data.success) {
                this.showNotification(data.message, 'success');
                setTimeout(() => window.location.reload(), 1000);
            } else {
                this.showNotification('Error marking all notifications as read', 'error');
            }
        } catch (error) {
            console.error('Error:', error);
            this.showNotification('Error marking all notifications as read', 'error');
        }
    }

    async deleteAllRead() {
        if (!confirm('Are you sure you want to delete all read notifications? This action cannot be undone.')) {
            return;
        }

        try {
            const response = await fetch('/office/notifications/delete-all-read', {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                }
            });

            const data = await response.json();
            
            if (data.success) {
                this.showNotification(data.message, 'success');
                setTimeout(() => window.location.reload(), 1000);
            } else {
                this.showNotification('Error deleting read notifications', 'error');
            }
        } catch (error) {
            console.error('Error:', error);
            this.showNotification('Error deleting read notifications', 'error');
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

    showNotification(message, type = 'info') {
        // Use the global showNotification function from officebase.js
        if (window.showNotification) {
            window.showNotification('Notification', message, type);
        } else {
            console.log(`${type.toUpperCase()}: ${message}`);
        }
    }
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
