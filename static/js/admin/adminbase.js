// Admin Base JavaScript - Socket.IO and Dashboard Manager
console.log("Initializing Admin Base");

class SocketManager {
    constructor() {
        this.socket = null;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.eventHandlers = new Map();
    }

    connect() {
        try {
            // Connect to the dashboard namespace
            this.socket = io('/dashboard', {
                transports: ['websocket', 'polling'],
                timeout: 5000,
                forceNew: true
            });

            this.setupEventHandlers();
            console.log('Dashboard socket connection initiated');
        } catch (error) {
            console.error('Error creating socket connection:', error);
            this.handleReconnection();
        }
    }

    setupEventHandlers() {
        if (!this.socket) return;

        this.socket.on('connect', () => {
            console.log('Connected to dashboard namespace');
            this.isConnected = true;
            this.reconnectAttempts = 0;
            
            // Request initial dashboard data
            this.socket.emit('request_dashboard_update');
            
            // Show connection status
            // this.showConnectionStatus('Connected to real-time dashboard', 'success');
        });

        this.socket.on('disconnect', (reason) => {
            console.log('Disconnected from dashboard:', reason);
            this.isConnected = false;
            // Suppress noisy warning when user is navigating away (normal page change)
            if (!window.__page_unloading) {
                this.showConnectionStatus('Disconnected from real-time dashboard', 'warning');
            }
            if (reason === 'io server disconnect' && !window.__page_unloading) {
                // Server disconnected unexpectedly, try to reconnect
                this.handleReconnection();
            }
        });

        this.socket.on('connect_error', (error) => {
            console.error('Dashboard connection error:', error);
            this.isConnected = false;
            this.showConnectionStatus('Connection error - retrying...', 'error');
            this.handleReconnection();
        });

        this.socket.on('dashboard_connected', (data) => {
            console.log('Dashboard connection confirmed:', data);
        });

        this.socket.on('dashboard_update', (data) => {
            console.log('Dashboard update received:', data);
            this.triggerEvent('dashboard_update', data);
        });

        this.socket.on('new_inquiry', (data) => {
            console.log('New inquiry event:', data);
            this.triggerEvent('new_inquiry', data);
        });

        this.socket.on('resolved_inquiry', (data) => {
            console.log('Resolved inquiry event:', data);
            this.triggerEvent('resolved_inquiry', data);
        });

        this.socket.on('new_session', (data) => {
            console.log('New session event:', data);
            this.triggerEvent('new_session', data);
        });

        this.socket.on('system_log', (data) => {
            console.log('System log event:', data);
            this.triggerEvent('system_log', data);
        });
    }

    handleReconnection() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('Max reconnection attempts reached');
            this.showConnectionStatus('Unable to connect to real-time dashboard', 'error');
            return;
        }

        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1); // Exponential backoff
        
        console.log(`Attempting to reconnect in ${delay}ms (attempt ${this.reconnectAttempts})`);
        
        setTimeout(() => {
            if (!this.isConnected) {
                this.connect();
            }
        }, delay);
    }

    on(event, handler) {
        if (!this.eventHandlers.has(event)) {
            this.eventHandlers.set(event, []);
        }
        this.eventHandlers.get(event).push(handler);
    }

    off(event, handler) {
        if (this.eventHandlers.has(event)) {
            const handlers = this.eventHandlers.get(event);
            const index = handlers.indexOf(handler);
            if (index > -1) {
                handlers.splice(index, 1);
            }
        }
    }

    triggerEvent(event, data) {
        if (this.eventHandlers.has(event)) {
            this.eventHandlers.get(event).forEach(handler => {
                try {
                    handler(data);
                } catch (error) {
                    console.error(`Error in event handler for ${event}:`, error);
                }
            });
        }
    }

    emit(event, data) {
        if (this.socket && this.isConnected) {
            this.socket.emit(event, data);
        } else {
            console.warn('Socket not connected, cannot emit event:', event);
        }
    }

    showConnectionStatus(message, type) {
        // Create or update connection status indicator
        let statusElement = document.getElementById('connection-status');
        
        if (!statusElement) {
            statusElement = document.createElement('div');
            statusElement.id = 'connection-status';
            statusElement.className = 'fixed top-4 right-4 z-50 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300';
            document.body.appendChild(statusElement);
        }

        // Remove existing type classes
        statusElement.classList.remove('bg-green-100', 'text-green-800', 'bg-yellow-100', 'text-yellow-800', 'bg-red-100', 'text-red-800');

        // Add appropriate styling based on type
        switch (type) {
            case 'success':
                statusElement.classList.add('bg-green-100', 'text-green-800');
                break;
            case 'warning':
                statusElement.classList.add('bg-yellow-100', 'text-yellow-800');
                break;
            case 'error':
                statusElement.classList.add('bg-red-100', 'text-red-800');
                break;
        }

        statusElement.textContent = message;
        statusElement.style.opacity = '1';

        // Auto-hide success messages
        if (type === 'success') {
            setTimeout(() => {
                if (statusElement) {
                    statusElement.style.opacity = '0';
                    setTimeout(() => {
                        if (statusElement && statusElement.parentNode) {
                            statusElement.parentNode.removeChild(statusElement);
                        }
                    }, 300);
                }
            }, 3000);
        }
    }

    disconnect() {
        if (this.socket) {
            this.socket.disconnect();
            this.socket = null;
            this.isConnected = false;
        }
    }
}

// Global socket manager instance
let socketManager = null;

// Initialize socket manager when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Only initialize socket manager on admin pages
    if (window.location.pathname.includes('/admin/')) {
        console.log('Initializing socket manager for admin dashboard');
        socketManager = new SocketManager();
        socketManager.connect();
        
        // Make socket manager available globally
        window.socketManager = socketManager;
    }
});

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    // Flag to indicate intentional navigation/unload so we don't show disconnect warning
    window.__page_unloading = true;
    if (socketManager) {
        socketManager.disconnect();
    }
});

// Enhanced notification system
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

// Make notification function globally available
window.showNotification = showNotification;

console.log('Admin base JavaScript initialized');