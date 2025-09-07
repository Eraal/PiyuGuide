/**
 * Smart Notifications Manager for Office Module
 * Handles intelligent notification stacking and real-time updates
 */

class SmartNotificationsManager {
    constructor() {
        this.csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        this.lastNotificationCheck = Date.now();
        this.checkInterval = 30000; // Check every 30 seconds
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.startPeriodicChecks();
        this.setupNotificationSounds();
    }

    setupEventListeners() {
        // Listen for page visibility changes to update notifications
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) {
                this.checkForNewNotifications();
            }
        });

        // Listen for focus events to update notifications
        window.addEventListener('focus', () => {
            this.checkForNewNotifications();
        });
    }

    startPeriodicChecks() {
        // Check for new notifications periodically
        setInterval(() => {
            this.checkForNewNotifications();
        }, this.checkInterval);
    }

    setupNotificationSounds() {
        // Ensure notification sound is loaded
        const sound = document.getElementById('notification-sound');
        if (sound) {
            sound.load();
        }
    }

    async checkForNewNotifications() {
        try {
            const response = await fetch('/office/notifications/get-unread-count', {
                method: 'GET',
                headers: {
                    'X-CSRFToken': this.csrfToken
                }
            });

            if (response.ok) {
                const data = await response.json();
                this.updateNotificationBadge(data.unread_count);
                
                // Check if there are new notifications since last check
                if (data.unread_count > this.lastUnreadCount) {
                    const newDelta = data.unread_count - (this.lastUnreadCount||0);
                    const now = Date.now();
                    // Suppress duplicate pop if socket already delivered a notification recently
                    const lastSocket = window.__lastOfficeSocketNotificationAt || 0;
                    const suppress = (now - lastSocket) < 2500; // 2.5s window
                    if (!suppress) {
                        this.playNotificationSound();
                        this.showNewNotificationAlert(newDelta);
                    }
                }
                
                this.lastUnreadCount = data.unread_count;
            }
        } catch (error) {
            console.error('Error checking for new notifications:', error);
        }
    }

    updateNotificationBadge(count) {
    // Prefer the dedicated office bell badge if present
    const badge = document.getElementById('office-ann-badge') || document.querySelector('.notification-badge');
        const notificationLink = document.querySelector('a[href*="office_notifications"]');
        
        if (count > 0) {
            if (badge) {
                badge.textContent = count;
                badge.style.display = 'inline-block';
            } else if (notificationLink) {
                // Create badge if it doesn't exist
                const newBadge = document.createElement('span');
                newBadge.className = 'notification-badge ml-auto counter-badge counter-red';
                newBadge.textContent = count;
                notificationLink.appendChild(newBadge);
            }
        } else {
            if (badge) {
                badge.style.display = 'none';
            }
        }
    }

    playNotificationSound() {
        const sound = document.getElementById('notification-sound');
        if (sound) {
            sound.play().catch(e => console.warn('Could not play notification sound:', e));
        }
    }

    showNewNotificationAlert(newCount) {
        // Show a subtle notification alert
        const alertElement = document.createElement('div');
        alertElement.className = 'fixed top-4 right-4 z-50 bg-green-600 text-white px-4 py-2 rounded-lg shadow-lg transform translate-x-full transition-transform duration-300';
        alertElement.innerHTML = `
            <div class="flex items-center space-x-2">
                <i class="fas fa-bell"></i>
                <span>${newCount} new notification${newCount > 1 ? 's' : ''}</span>
            </div>
        `;
        
        document.body.appendChild(alertElement);
        
        // Animate in
        setTimeout(() => {
            alertElement.classList.remove('translate-x-full');
        }, 100);
        
        // Animate out after 3 seconds
        setTimeout(() => {
            alertElement.classList.add('translate-x-full');
            setTimeout(() => {
                if (alertElement.parentNode) {
                    alertElement.parentNode.removeChild(alertElement);
                }
            }, 300);
        }, 3000);
    }

    async markNotificationAsRead(notificationId) {
        try {
            const response = await fetch(`/office/notifications/mark-read/${notificationId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                }
            });

            if (response.ok) {
                this.checkForNewNotifications();
                return true;
            }
        } catch (error) {
            console.error('Error marking notification as read:', error);
        }
        return false;
    }

    async getNotificationSummary() {
        try {
            const response = await fetch('/office/notifications/summary', {
                method: 'GET',
                headers: {
                    'X-CSRFToken': this.csrfToken
                }
            });

            if (response.ok) {
                return await response.json();
            }
        } catch (error) {
            console.error('Error getting notification summary:', error);
        }
        return null;
    }

    async cleanupOldNotifications(daysOld = 30) {
        try {
            const response = await fetch('/office/notifications/cleanup-old', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                },
                body: JSON.stringify({ days_old: daysOld })
            });

            if (response.ok) {
                const data = await response.json();
                this.showSuccessMessage(`Cleaned up ${data.cleaned_count} old notifications`);
                return data.cleaned_count;
            }
        } catch (error) {
            console.error('Error cleaning up old notifications:', error);
        }
        return 0;
    }

    showSuccessMessage(message) {
        // Show success message using existing notification system
        if (typeof showNotification === 'function') {
            showNotification('Success', message, 'success');
        } else {
            console.log(message);
        }
    }

    // Method to group notifications by inquiry for better display
    groupNotificationsByInquiry(notifications) {
        const grouped = {};
        
        notifications.forEach(notification => {
            if (notification.inquiry_id) {
                const key = `inquiry_${notification.inquiry_id}`;
                if (!grouped[key]) {
                    grouped[key] = {
                        inquiry_id: notification.inquiry_id,
                        student_name: notification.title.includes('from') ? 
                            notification.title.split('from')[1].split(' -')[0].trim() : 'Unknown',
                        notifications: [],
                        latest_activity: notification.created_at,
                        unread_count: 0
                    };
                }
                grouped[key].notifications.push(notification);
                if (!notification.is_read) {
                    grouped[key].unread_count++;
                }
                if (new Date(notification.created_at) > new Date(grouped[key].latest_activity)) {
                    grouped[key].latest_activity = notification.created_at;
                }
            }
        });
        
        return Object.values(grouped);
    }

    // Method to format notification display with smart stacking
    formatStackedNotification(group) {
        const count = group.unread_count;
        const studentName = group.student_name;
        
        if (count > 1) {
            return `${count} new messages from ${studentName}`;
        } else if (count === 1) {
            return `New message from ${studentName}`;
        } else {
            return `Previous messages from ${studentName}`;
        }
    }
}

// Global function for onclick handlers
window.markNotificationAsRead = function(notificationId) {
    if (window.smartNotificationsManager) {
        window.smartNotificationsManager.markNotificationAsRead(notificationId);
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Only initialize on office pages
    if (window.location.pathname.includes('/office/')) {
        window.smartNotificationsManager = new SmartNotificationsManager();
        
        // Add cleanup button to notifications page if it exists
        const notificationsPage = document.querySelector('.notifications-page');
        if (notificationsPage) {
            const cleanupBtn = document.createElement('button');
            cleanupBtn.className = 'btn btn-sm btn-outline-secondary';
            cleanupBtn.innerHTML = '<i class="fas fa-trash-alt mr-1"></i> Clean Old Notifications';
            cleanupBtn.onclick = () => {
                if (confirm('This will permanently delete all read notifications older than 30 days. Continue?')) {
                    window.smartNotificationsManager.cleanupOldNotifications(30);
                }
            };
            
            const actionsContainer = document.querySelector('.notifications-actions');
            if (actionsContainer) {
                actionsContainer.appendChild(cleanupBtn);
            }
        }
    }
});

// Export for potential use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SmartNotificationsManager;
}
