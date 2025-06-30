/**
 * Office Base JavaScript
 * Common functionality for office module pages
 */

// Show notification function similar to adminbase.js
function showNotification(title, message, type = 'info', duration = 5000) {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `fixed top-20 right-4 z-50 max-w-sm bg-white border-l-4 rounded-lg shadow-lg transform translate-x-full transition-all duration-300 ease-out`;
    
    // Add type-specific styling
    switch (type) {
        case 'success':
            notification.classList.add('border-green-500');
            break;
        case 'error':
            notification.classList.add('border-red-500');
            break;
        case 'warning':
            notification.classList.add('border-yellow-500');
            break;
        default:
            notification.classList.add('border-blue-500');
    }
    
    notification.innerHTML = `
        <div class="p-4">
            <div class="flex items-start">
                <div class="flex-shrink-0">
                    <i class="fas ${getNotificationIcon(type)} text-${getNotificationColor(type)}-500"></i>
                </div>
                <div class="ml-3 w-0 flex-1">
                    <p class="text-sm font-medium text-gray-900">${title}</p>
                    <p class="mt-1 text-sm text-gray-500">${message}</p>
                </div>
                <div class="ml-4 flex-shrink-0 flex">
                    <button class="bg-white rounded-md inline-flex text-gray-400 hover:text-gray-500 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500" onclick="this.parentElement.parentElement.parentElement.parentElement.remove()">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(notification);
    
    // Animate in
    setTimeout(() => {
        notification.classList.remove('translate-x-full');
    }, 100);
    
    // Auto-remove after duration
    setTimeout(() => {
        notification.classList.add('translate-x-full');
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, duration);
}

// Helper functions for notification icons and colors
function getNotificationIcon(type) {
    switch (type) {
        case 'success': return 'fa-check-circle';
        case 'error': return 'fa-exclamation-circle';
        case 'warning': return 'fa-exclamation-triangle';
        default: return 'fa-info-circle';
    }
}

function getNotificationColor(type) {
    switch (type) {
        case 'success': return 'green';
        case 'error': return 'red';
        case 'warning': return 'yellow';
        default: return 'blue';
    }
}

// Notification count updater
function updateNotificationCount() {
    fetch('/office/notifications/get-unread-count')
        .then(response => response.json())
        .then(data => {
            const badge = document.querySelector('.counter-badge.counter-red');
            const notificationLink = document.querySelector('a[href*="office_notifications"]');
            
            if (data.unread_count > 0) {
                if (badge) {
                    badge.textContent = data.unread_count;
                } else if (notificationLink) {
                    // Create badge if it doesn't exist
                    const newBadge = document.createElement('span');
                    newBadge.className = 'ml-auto counter-badge counter-red';
                    newBadge.textContent = data.unread_count;
                    notificationLink.appendChild(newBadge);
                }
            } else {
                if (badge) {
                    badge.remove();
                }
            }
        })
        .catch(error => console.error('Error updating notification count:', error));
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Update notification count every 30 seconds
    updateNotificationCount();
    setInterval(updateNotificationCount, 30000);
    
    // Handle flash messages
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(message => {
        setTimeout(() => {
            message.style.opacity = '0';
            setTimeout(() => {
                message.remove();
            }, 300);
        }, 5000);
    });
});

// Export functions for global use
window.showNotification = showNotification;
window.updateNotificationCount = updateNotificationCount;