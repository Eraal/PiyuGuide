/**
 * OfficeChatSocketManager - Handles WebSocket chat interaction for office admins
 * This is a dedicated module for handling chat functionality that's
 * completely isolated from other real-time features.
 */
class OfficeChatSocketManager {
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
            onError: null
        };
        
        // Reconnection settings
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectInterval = 3000; // 3 seconds
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
            if (message.sender_id !== this._getCurrentUserId()) {
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
        
        this.socket.on('message_sent', data => {
            if (this.messageCallbacks.onMessageSent) {
                this.messageCallbacks.onMessageSent(data);
            }
        });
        
        this.socket.on('message_read', data => {
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
        
        // If already in a room, leave it first
        if (this.currentInquiryId) {
            this.leaveCurrentRoom();
        }
        
        this.currentInquiryId = inquiryId;
        this.socket.emit('join_inquiry_room', { inquiry_id: inquiryId });
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
    module.exports = OfficeChatSocketManager;
} else {
    window.OfficeChatSocketManager = OfficeChatSocketManager;
} 