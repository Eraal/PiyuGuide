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
            // Target only the Notifications nav item
            const notificationLink = document.getElementById('nav-notifications') || document.querySelector('a[href*="office_notifications"]');
            const badge = notificationLink ? notificationLink.querySelector('.counter-badge.counter-red') : null;
            
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
            } else if (badge) {
                // Hide instead of remove to avoid layout shifts/flicker; server will control visibility on next render
                badge.textContent = '0';
                badge.classList.add('hidden');
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

    // Start presence heartbeat for office admins
    startOfficeHeartbeat();

    // Initialize Concern Types dropdown reliably
    try { initConcernTypesDropdown(); } catch (_) {}
});

// Export functions for global use
window.showNotification = showNotification;
window.updateNotificationCount = updateNotificationCount;

// --- Presence Heartbeat ---
function startOfficeHeartbeat() {
    // Avoid running on non-office pages without the base template
    // Also allow tests: guard on presence of connection/status nodes but don't require them
    const connectionEl = document.getElementById('office-connection-status');
    const statusEl = document.getElementById('staff-status-indicator');

    // Expose a global flag so templates can avoid simulated status changes
    try { window.__officePresenceHeartbeatActive = true; } catch (_) {}

    let consecutiveFailures = 0;
    const maxFailuresBeforeOffline = 3;
    const intervalMs = 60000; // 60s heartbeat

    function setConnectedUI(isConnected) {
        if (connectionEl) {
            connectionEl.className = 'connection-indicator ' + (isConnected ? 'connection-online' : 'connection-offline');
            connectionEl.title = isConnected ? 'Connected to presence service' : 'Disconnected from presence service';
        }
        if (statusEl) {
            statusEl.className = 'status-indicator ' + (isConnected ? 'status-online' : 'status-offline');
            statusEl.title = isConnected ? 'Online' : 'Offline';
        }
    }

    async function ping() {
        try {
            const res = await fetch('/office/api/heartbeat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    // CSRF token header will be auto-added in templates that override XHR open; for fetch, include if meta exists
                    'X-CSRFToken': (document.querySelector('meta[name="csrf-token"]')?.getAttribute('content')) || ''
                },
                body: JSON.stringify({ ts: Date.now() })
            });
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const data = await res.json();
            // Success
            consecutiveFailures = 0;
            setConnectedUI(true);
        } catch (e) {
            consecutiveFailures += 1;
            if (consecutiveFailures >= maxFailuresBeforeOffline) {
                setConnectedUI(false);
            }
            // Keep trying silently
        }
    }

    // Kick off immediately, then on interval
    ping();
    setInterval(ping, intervalMs);
}

// Concern Types dropdown (sidebar) robust initializer
function initConcernTypesDropdown() {
    const dropdown = document.getElementById('concernDropdown');
    const icon = document.getElementById('concernDropdownIcon');
    if (!dropdown || !icon) return;
    const button = icon.closest('button');
    if (!button) return;

    // Prevent duplicate listeners
    if (button.__concernDropdownInit) return;
    button.__concernDropdownInit = true;

    function setExpanded(expanded) {
        button.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        if (icon) icon.style.transform = expanded ? 'rotate(180deg)' : 'rotate(0deg)';
    }

    button.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const willOpen = dropdown.classList.contains('hidden');
        dropdown.classList.toggle('hidden');
        setExpanded(willOpen);
    });

    // Keyboard support
    button.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            const willOpen = dropdown.classList.contains('hidden');
            dropdown.classList.toggle('hidden');
            setExpanded(willOpen);
        }
    });

    document.addEventListener('click', (e) => {
        if (dropdown.classList.contains('hidden')) return;
        if (!button.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.classList.add('hidden');
            setExpanded(false);
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !dropdown.classList.contains('hidden')) {
            dropdown.classList.add('hidden');
            setExpanded(false);
        }
    });

    // Auto-open when current page marks one of the links active (bg-green-50)
    try {
        const activeLink = dropdown.querySelector('a.bg-green-50');
        if (activeLink) {
            dropdown.classList.remove('hidden');
            setExpanded(true);
        }
    } catch (_) {}
}