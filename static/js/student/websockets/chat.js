/**
 * ChatSocketManager - Handles WebSocket chat interaction for students
 * This is a dedicated module for handling chat functionality that's
 * completely isolated from other real-time features.
 */
class ChatSocketManager {
    /**
     * Initialize the chat socket manager
     * @param {string} serverUrl - The server URL (default: window.location.origin)
     */
    constructor(serverUrl = window.location.origin) {
        this.socket = null;
        this.serverUrl = serverUrl;
        this.connected = false;
        this.currentInquiryId = null;
        this.messageCallbacks = {
            onMessageReceived: null,
            onMessageSent: null,
            onMessageRead: null,
            onConnectionStatusChange: null,
            onError: null,
            onTyping: null,
            onStopTyping: null
        };
        
        // Reconnection settings
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectInterval = 3000; // 3 seconds
    }
    
    /**
     * Try to resolve the inquiry id from various sources
     * @private
     * @param {any} inquiryId
     * @returns {number|null}
     */
    _resolveInquiryId(inquiryId) {
        if (inquiryId !== undefined && inquiryId !== null && String(inquiryId).trim() !== '') {
            const n = parseInt(inquiryId, 10);
            if (!isNaN(n) && n > 0) return n;
        }
        try {
            const el = document.querySelector('[data-inquiry-id]');
            if (el) {
                const v = el.getAttribute('data-inquiry-id');
                const n = parseInt(v, 10);
                if (!isNaN(n) && n > 0) return n;
            }
        } catch (_) {}
        try {
            const hid = document.getElementById('inquiryId') || document.querySelector('input[name="inquiry_id"]');
            const v = hid && (hid.value || hid.getAttribute('value'));
            const n = parseInt(v, 10);
            if (!isNaN(n) && n > 0) return n;
        } catch (_) {}
        try {
            const path = (window.location && window.location.pathname) || '';
            const m = path.match(/\/(inquiry|view_inquiry)\/(\d+)/i) || path.match(/\/(\d+)(?:\/?$)/);
            if (m) {
                const n = parseInt(m[m.length - 1], 10);
                if (!isNaN(n) && n > 0) return n;
            }
        } catch (_) {}
        try {
            const p = new URLSearchParams(window.location.search);
            const v = p.get('inquiry_id');
            const n = parseInt(v, 10);
            if (!isNaN(n) && n > 0) return n;
        } catch (_) {}
        return null;
    }

    /**
     * Initialize and connect to the chat WebSocket
     * @returns {Promise} Resolves when connected
     */
    connect() {
        return new Promise((resolve, reject) => {
            if (this.socket && this.connected) {
                resolve();
                return;
            }
            
            // Create a dedicated socket connection for chat
            this.socket = io(`${this.serverUrl}/chat`, {
                reconnection: true,
                reconnectionAttempts: this.maxReconnectAttempts,
                reconnectionDelay: this.reconnectInterval
            });
            
            // Setup event listeners
            this._setupSocketEvents();
            
            // Set a timeout for connection
            const connectionTimeout = setTimeout(() => {
                if (!this.connected) {
                    reject(new Error('Connection timeout'));
                }
            }, 10000); // 10 second timeout
            
            // Wait for connect event
            this.socket.on('connect_response', data => {
                clearTimeout(connectionTimeout);
                this.connected = true;
                this.reconnectAttempts = 0;
                
                if (this.messageCallbacks.onConnectionStatusChange) {
                    this.messageCallbacks.onConnectionStatusChange(true);
                }
                
                console.log('Connected to chat WebSocket');
                resolve();
            });
        });
    }
    
    /**
     * Set up all socket event listeners
     * @private
     */
    _setupSocketEvents() {
        // Connection events
        this.socket.on('connect', () => {
            console.log('Socket.IO connection established');
        });
        
        this.socket.on('disconnect', () => {
            this.connected = false;
            
            if (this.messageCallbacks.onConnectionStatusChange) {
                this.messageCallbacks.onConnectionStatusChange(false);
            }
            
            console.log('Disconnected from chat WebSocket');
        });
        
        this.socket.on('connect_error', error => {
            console.error('Connection error:', error);
            
            if (this.messageCallbacks.onError) {
                this.messageCallbacks.onError('Connection failed. Please check your internet connection.');
            }
        });
        
        this.socket.on('reconnect_attempt', attemptNumber => {
            console.log(`Trying to reconnect: Attempt ${attemptNumber}`);
        });
        
        // Chat events
    this.socket.on('receive_message', message => {
            // For messages from other users, set is_current_user to false
            const myId = String(this._getCurrentUserId());
            if (String(message.sender_id) !== myId) {
                message.is_current_user = false;
            }
            
            if (this.messageCallbacks.onMessageReceived) {
                this.messageCallbacks.onMessageReceived(message);
            }
            
            // If message is not from current user, mark it as read
            if (!message.is_current_user) {
                this.markMessageAsRead(message.id);
            }
        });
        
        // Typing events
        this.socket.on('typing', data => {
            if (this.messageCallbacks.onTyping) {
                this.messageCallbacks.onTyping(data);
            }
        });
        this.socket.on('stop_typing', data => {
            if (this.messageCallbacks.onStopTyping) {
                this.messageCallbacks.onStopTyping(data);
            }
        });

        this.socket.on('message_sent', data => {
            if (this.messageCallbacks.onMessageSent) {
                this.messageCallbacks.onMessageSent(data);
            }
        });
        
        this.socket.on('message_read', data => {
            // Update UI icon for the read message if callback provided
            if (this.messageCallbacks.onMessageRead) {
                this.messageCallbacks.onMessageRead(data);
            }
        });
        
        this.socket.on('error', error => {
            console.error('Socket error:', error);
            
            if (this.messageCallbacks.onError) {
                this.messageCallbacks.onError(error.message || 'An error occurred');
            }
        });
        
        this.socket.on('room_joined', data => {
            console.log(`Joined room for inquiry ${data.inquiry_id}`);
        });
    }
    
    /**
     * Get the current user ID from the page data
     * @private
     * @returns {number} The current user ID
     */
    _getCurrentUserId() {
        // This assumes there's a global currentUserId variable or data attribute available
        return window.currentUserId || document.body.getAttribute('data-user-id');
    }
    
    /**
     * Join a chat room for a specific inquiry
     * @param {number} inquiryId - The ID of the inquiry to join
     */
    joinInquiryRoom(inquiryId) {
        if (!this.connected) {
            if (this.messageCallbacks.onError) {
                this.messageCallbacks.onError('Not connected to chat server');
            }
            return;
        }
        // Resolve inquiryId robustly
        const resolvedId = this._resolveInquiryId(inquiryId);
        if (!resolvedId) {
            if (this.messageCallbacks.onError) {
                this.messageCallbacks.onError('Inquiry ID is required');
            }
            return;
        }
        this.currentInquiryId = resolvedId;
        this.socket.emit('join_inquiry_room', { inquiry_id: resolvedId });

        // After a short delay, auto-mark any visible incoming messages as read
        setTimeout(() => {
            try {
                const bubbles = document.querySelectorAll('#messageHistory .message-bubble');
                bubbles.forEach(b => {
                    const senderId = b.getAttribute('data-sender-id');
                    const msgId = b.getAttribute('data-message-id');
                    if (msgId && senderId && String(senderId) !== String(this._getCurrentUserId())) {
                        this.markMessageAsRead(msgId);
                    }
                });
            } catch (e) {}
        }, 300);
    }
    
    /**
     * Leave the current inquiry chat room
     */
    leaveCurrentRoom() {
        if (this.currentInquiryId && this.connected) {
            this.socket.emit('leave_inquiry_room', { inquiry_id: this.currentInquiryId });
            this.currentInquiryId = null;
        }
    }
    
    /**
     * Send a chat message
     * @param {string} content - The message content
     * @returns {boolean} Whether the message was sent
     */
    sendMessage(content) {
        if (!this.connected || !this.currentInquiryId) {
            if (this.messageCallbacks.onError) {
                this.messageCallbacks.onError('Not connected to chat or no inquiry selected');
            }
            return false;
        }
        
        if (!content || content.trim() === '') {
            if (this.messageCallbacks.onError) {
                this.messageCallbacks.onError('Message cannot be empty');
            }
            return false;
        }
        
        this.socket.emit('send_message', {
            inquiry_id: this.currentInquiryId,
            content: content
        });
    // After sending, ensure stop typing is emitted
    this.stopTyping();
        
        return true;
    }
    
    /**
     * Mark a message as read
     * @param {number} messageId - The ID of the message to mark as read
     */
    markMessageAsRead(messageId) {
        if (this.connected) {
            this.socket.emit('mark_as_read', { message_id: messageId });
        }
    }
    
    /**
     * Register a callback for when a message is received
     * @param {Function} callback - The callback function
     */
    onMessageReceived(callback) {
        this.messageCallbacks.onMessageReceived = callback;
    }
    
    /**
     * Register a callback for when a message is sent successfully
     * @param {Function} callback - The callback function
     */
    onMessageSent(callback) {
        this.messageCallbacks.onMessageSent = callback;
    }
    
    /**
     * Register a callback for when a message is read by the recipient
     * @param {Function} callback - The callback function
     */
    onMessageRead(callback) {
        this.messageCallbacks.onMessageRead = callback;
    }
    
    /**
     * Register a callback for connection status changes
     * @param {Function} callback - The callback function
     */
    onConnectionStatusChange(callback) {
        this.messageCallbacks.onConnectionStatusChange = callback;
    }
    
    /**
     * Register a callback for errors
     * @param {Function} callback - The callback function
     */
    onError(callback) {
        this.messageCallbacks.onError = callback;
    }
    
    /**
     * Register a callback for when the other party is typing
     * @param {Function} callback
     */
    onTyping(callback) {
        this.messageCallbacks.onTyping = callback;
    }
    
    /**
     * Register a callback for when the other party stops typing
     * @param {Function} callback
     */
    onStopTyping(callback) {
        this.messageCallbacks.onStopTyping = callback;
    }
    
    /**
     * Emit typing event with debounce
     */
    startTyping() {
        if (!this.connected || !this.currentInquiryId) return;
        // Use a simple throttle to avoid flooding
        const now = Date.now();
        if (!this._lastTypingEmit || now - this._lastTypingEmit > 1500) {
            this.socket.emit('typing', { inquiry_id: this.currentInquiryId });
            this._lastTypingEmit = now;
        }
        clearTimeout(this._typingTimeout);
        this._typingTimeout = setTimeout(() => this.stopTyping(), 2000);
    }
    
    stopTyping() {
        if (!this.connected || !this.currentInquiryId) return;
        this.socket.emit('stop_typing', { inquiry_id: this.currentInquiryId });
    }
    
    /**
     * Disconnect from the chat WebSocket
     */
    disconnect() {
        if (this.socket) {
            if (this.currentInquiryId) {
                this.leaveCurrentRoom();
            }
            
            this.socket.disconnect();
            this.connected = false;
        }
    }
}

// Export as a global object or as an ES module
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ChatSocketManager;
} else {
    window.ChatSocketManager = ChatSocketManager;
} 