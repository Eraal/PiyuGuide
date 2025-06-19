// This is the logic for websockets in the counseling page

// Video Counseling WebSocket Client for Students
class VideoCounselingClient {
    constructor(sessionId, currentUserId = null) {
        this.sessionId = sessionId;
        this.currentUserId = currentUserId;
        this.socket = null;
        this.peerConnection = null;
        this.localStream = null;
        this.remoteStream = null;
        this.isConnected = false;
        this.isAudioEnabled = true;
        this.isVideoEnabled = true;
        this.isScreenSharing = false;
        this.screenStream = null;
        this.role = 'student'; // or 'counselor' for office
        this.otherParticipant = null;
        this.chatMessages = [];
        this.pendingIceCandidates = [];
        this.reconnectionAttempts = 0;
        this.mediaDevicesSupported = Boolean(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
        this.isHttps = location.protocol === 'https:' || 
                      location.hostname === 'localhost' || 
                      location.hostname === '127.0.0.1' ||
                      location.hostname.endsWith('.localhost');
        
        // Check if we're in a secure context for media access
        this.isSecureContext = window.isSecureContext || this.isHttps;
        
        // Track mock media state
        this.hasMockVideo = false;
        this.hasMockAudio = false;
        this.mockVideoCanvas = null;
        
        // More flexible media constraints with fallbacks
        this.mediaConstraints = {
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
            },
            video: {
                width: { ideal: 1280, min: 640 },
                height: { ideal: 720, min: 480 },
                facingMode: "user"
            }
        };
        
        this.peerConnectionConfig = {
            iceServers: [
                { urls: 'stun:stun.l.google.com:19302' },
                { urls: 'stun:stun1.l.google.com:19302' }
            ],
            iceCandidatePoolSize: 10
        };

        // Event callbacks
        this.onStatusChange = null;
        this.onRemoteStreamUpdate = null;
        this.onLocalStreamUpdate = null;
        this.onChatMessage = null;
        this.onParticipantJoined = null;
        this.onParticipantLeft = null;
        this.onCallStarted = null;
        this.onCallEnded = null;
        this.onError = null;
        this.onAudioStateChanged = null;
        this.onVideoStateChanged = null;
        this.onDeviceChange = null;
        
        // Set up device change listener
        if (navigator.mediaDevices && navigator.mediaDevices.ondevicechange !== undefined) {
            navigator.mediaDevices.ondevicechange = this.handleDeviceChange.bind(this);
        }
    }

    // Initialize the connection with improved permission handling
    async init() {
        try {
            console.log('Initializing video counseling client...');
            
            // First check browser compatibility
            if (!this.checkBrowserCompatibility()) {
                return false;
            }
            
            // Connect to WebSocket server
            this.socket = io('/video-counseling', {
                transports: ['websocket'],
                upgrade: false
            });
            
            // Set up socket event listeners
            this.setupSocketListeners();
            
            // Check and request media permissions early
            this.updateStatus('Checking media devices...');
            const mediaResult = await this.setupLocalMedia();
            
            if (!mediaResult) {
                console.warn('Media setup failed, but continuing with connection...');
                this.updateStatus('Connected without media devices');
            } else {
                this.updateStatus('Media devices ready');
            }
            
            // Always continue to connect even if media fails
            this.updateStatus('Connecting to session...');
            
            return true;
        } catch (error) {
            console.error('Error initializing video counseling client:', error);
            this.handleError(error);
            return false;
        }
    }

    // Check browser compatibility
    checkBrowserCompatibility() {
        const issues = [];
        
        if (!window.WebSocket && !window.io) {
            issues.push('WebSocket support');
        }
        
        if (!navigator.mediaDevices) {
            issues.push('Media devices API');
        }
        
        if (!window.RTCPeerConnection) {
            issues.push('WebRTC support');
        }
        
        if (issues.length > 0) {
            const message = `Your browser is missing support for: ${issues.join(', ')}. Please update your browser or try a different one.`;
            this.showBrowserCompatibilityError(message);
            return false;
        }
        
        return true;
    }

    // Show browser compatibility error
    showBrowserCompatibilityError(message) {
        const dialog = document.createElement('div');
        dialog.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
        
        dialog.innerHTML = `
            <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4 shadow-xl">
                <div class="flex items-center mb-4">
                    <div class="flex-shrink-0 w-10 h-10 bg-red-50 border-red-200 rounded-full flex items-center justify-center mr-3">
                        <i class="fas fa-exclamation-triangle text-red-500"></i>
                    </div>
                    <h3 class="text-lg font-semibold text-gray-900">Browser Not Supported</h3>
                </div>
                <p class="text-gray-700 mb-4">${message}</p>
                <div class="bg-blue-50 border border-blue-200 rounded p-3 mb-4">
                    <p class="text-sm text-blue-800">
                        <strong>Recommended browsers:</strong><br>
                        Chrome 60+, Firefox 60+, Safari 11+, Edge 79+
                    </p>
                </div>
                <div class="flex justify-end">
                    <button onclick="window.location.reload()" class="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600">
                        Refresh Page
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(dialog);
    }

    // Set up socket event listeners
    setupSocketListeners() {
        console.log('Setting up socket listeners...');
        
        this.socket.on('connect', () => {
            console.log('Connected to video counseling server');
            this.isConnected = true;
            this.joinSession();
        });

        this.socket.on('disconnect', () => {
            console.log('Disconnected from video counseling server');
            this.isConnected = false;
            this.updateStatus('Disconnected from server');
        });

        this.socket.on('connection_success', (data) => {
            console.log('Connection success:', data);
        });

        this.socket.on('error', (data) => {
            console.error('Socket error:', data);
            this.handleError(new Error(data.message));
        });

        this.socket.on('session_joined', (data) => {
            console.log('Session joined:', data);
            this.role = data.user_role;
            this.otherParticipant = data.other_participant;
            
            // Update waiting room status
            this.updateStatus(this.getStatusMessage(data.waiting_room_status));
            
            // If call has already started, create peer connection
            if (data.call_started) {
                this.createPeerConnection();
                if (this.otherParticipant) {
                    this.initiateCall();
                }
            }
            
            // Notify about participant info
            if (this.otherParticipant && this.onParticipantJoined) {
                this.onParticipantJoined(this.otherParticipant);
            }
        });

        this.socket.on('user_joined', (data) => {
            console.log('User joined:', data);
            
            // Store other participant info
            if (data.role !== this.role) {
                this.otherParticipant = {
                    user_id: data.user_id,
                    username: data.username,
                    role: data.role
                };
                
                // Notify about participant joined
                if (this.onParticipantJoined) {
                    this.onParticipantJoined(this.otherParticipant);
                }
            }
            
            // Update waiting room status
            this.updateStatus(this.getStatusMessage(data.waiting_room_status));
        });

        this.socket.on('user_left', (data) => {
            console.log('User left:', data);
            
            // Check if it was the other participant
            if (this.otherParticipant && this.otherParticipant.user_id === data.user_id) {
                // Notify about participant left
                if (this.onParticipantLeft) {
                    this.onParticipantLeft(this.otherParticipant);
                }
                
                // Update status
                this.updateStatus('The other participant has left the session');
                
                // Close peer connection
                this.closePeerConnection();
                
                // Clear other participant
                this.otherParticipant = null;
            }
        });

        this.socket.on('start_call', (data) => {
            console.log('Start call:', data);
            
            // Create peer connection
            this.createPeerConnection();
            
            // If student, wait for offer from counselor
            // If counselor, initiate call
            if (this.role === 'counselor' && this.otherParticipant) {
                this.initiateCall();
            }
            
            // Update status
            this.updateStatus('Call started');
            
            // Notify call started
            if (this.onCallStarted) {
                this.onCallStarted(data);
            }
        });

        this.socket.on('session_ended', (data) => {
            console.log('Session ended:', data);
            
            // Update status
            this.updateStatus('Session ended');
            
            // Close peer connection
            this.closePeerConnection();
            
            // Notify call ended
            if (this.onCallEnded) {
                this.onCallEnded(data);
            }
        });

        this.socket.on('offer', async (data) => {
            console.log('Received offer:', data);
            
            if (!this.peerConnection) {
                this.createPeerConnection();
            }
            
            try {
                await this.peerConnection.setRemoteDescription(new RTCSessionDescription(data.offer));
                console.log('Set remote description (offer)');
                
                const answer = await this.peerConnection.createAnswer();
                await this.peerConnection.setLocalDescription(answer);
                console.log('Created and set local description (answer)');
                
                this.socket.emit('answer', {
                    target: data.sender,
                    session_id: this.sessionId,
                    answer: answer
                });
                
                // Send any pending ICE candidates now that remote description is set
                this.sendPendingIceCandidates();
            } catch (error) {
                console.error('Error handling offer:', error);
                this.handleError(error);
            }
        });

        this.socket.on('answer', async (data) => {
            console.log('Received answer:', data);
            
            try {
                await this.peerConnection.setRemoteDescription(new RTCSessionDescription(data.answer));
                console.log('Set remote description (answer)');
                
                // Send any pending ICE candidates now that remote description is set
                this.sendPendingIceCandidates();
            } catch (error) {
                console.error('Error handling answer:', error);
                this.handleError(error);
            }
        });

        this.socket.on('ice_candidate', async (data) => {
            console.log('Received ICE candidate');
            
            try {
                if (this.peerConnection) {
                    await this.peerConnection.addIceCandidate(new RTCIceCandidate(data.candidate));
                    console.log('Added ICE candidate');
                }
            } catch (error) {
                console.error('Error handling ICE candidate:', error);
            }
        });

        this.socket.on('audio_state_changed', (data) => {
            console.log('Audio state changed:', data);
            
            // Notify about audio state change
            if (this.onAudioStateChanged) {
                this.onAudioStateChanged(data);
            }
        });

        this.socket.on('video_state_changed', (data) => {
            console.log('Video state changed:', data);
            
            // Notify about video state change
            if (this.onVideoStateChanged) {
                this.onVideoStateChanged(data);
            }
        });

        this.socket.on('chat_message', (data) => {
            console.log('Received chat message:', data);
            
            // Add message to chat history
            this.chatMessages.push(data);
            
            // Notify about new message
            if (this.onChatMessage) {
                this.onChatMessage(data);
            }
        });
    }

    // Join the session
    joinSession() {
        if (!this.isConnected) {
            console.error('Cannot join session: not connected to server');
            return;
        }
        
        console.log('Joining session:', this.sessionId);
        this.socket.emit('join_session', {
            session_id: this.sessionId
        });
    }

    // Leave the session
    leaveSession() {
        if (!this.isConnected) {
            console.log('Not connected to server, no need to leave session');
            return;
        }
        
        console.log('Leaving session:', this.sessionId);
        this.socket.emit('leave_session', {
            session_id: this.sessionId
        });
        
        // Close peer connection
        this.closePeerConnection();
        
        // Stop local media
        this.stopLocalMedia();
        
        // Disconnect socket
        this.socket.disconnect();
    }

    // Set up local media with improved permission handling
    async setupLocalMedia() {
        try {
            console.log('Setting up local media...');
            
            // Check if media devices are available
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                throw new Error('Your browser does not support media devices access. Please update your browser.');
            }
            
            // For non-secure contexts, provide specific guidance
            if (!this.isSecureContext) {
                const currentUrl = window.location.href;
                const httpsUrl = currentUrl.replace('http://', 'https://');
                const helpMessage = `
                    <p>Media access requires a secure connection (HTTPS). Your current connection is not secure.</p>
                    <div class="mt-4 p-3 bg-blue-50 border border-blue-200 rounded">
                        <p class="text-sm text-blue-800"><strong>Solutions:</strong></p>
                        <ul class="text-sm text-blue-700 mt-2 space-y-1">
                            <li>• Try accessing via: <a href="${httpsUrl}" class="underline font-mono">${httpsUrl}</a></li>
                            <li>• Contact your administrator to enable HTTPS</li>
                            <li>• For development: use localhost instead of IP address</li>
                        </ul>
                    </div>
                `;
                this.showPermissionDialog(helpMessage, true);
                throw new Error('Media access requires HTTPS or localhost');
            }
            
            // First, request permission explicitly with a user-friendly approach
            return await this.requestMediaPermissions();
            
        } catch (error) {
            console.error('Error setting up local media:', error);
            this.handleError(error);
            return false;
        }
    }

    // Request media permissions with better UX
    async requestMediaPermissions() {
        try {
            // First check what devices are available (without requesting permission yet)
            let hasVideoInput = false;
            let hasAudioInput = false;
            
            try {
                const devices = await navigator.mediaDevices.enumerateDevices();
                hasVideoInput = devices.some(device => device.kind === 'videoinput' && device.deviceId);
                hasAudioInput = devices.some(device => device.kind === 'audioinput' && device.deviceId);
            } catch (deviceError) {
                console.warn('Could not enumerate devices:', deviceError);
                // Assume devices are available and let getUserMedia tell us otherwise
                hasVideoInput = true;
                hasAudioInput = true;
            }
            
            if (!hasVideoInput && !hasAudioInput) {
                throw new Error('No camera or microphone detected. Please connect a camera or microphone and try again.');
            }
            
            // Show permission request dialog
            this.showPermissionDialog('We need access to your camera and microphone for the video session. Please click "Allow" when prompted by your browser.');
            
            // Build constraints with graceful degradation
            const constraints = {
                audio: hasAudioInput ? {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                } : false,
                video: hasVideoInput ? {
                    width: { ideal: 1280, max: 1920, min: 640 },
                    height: { ideal: 720, max: 1080, min: 480 },
                    facingMode: "user",
                    frameRate: { ideal: 30, max: 60, min: 15 }
                } : false
            };
            
            // Request permissions step by step for better error handling
            if (hasAudioInput && hasVideoInput) {
                return await this.requestBothMediaTypes(constraints);
            } else if (hasAudioInput) {
                return await this.requestAudioOnly();
            } else if (hasVideoInput) {
                return await this.requestVideoOnly();
            } else {
                throw new Error('No suitable media devices found');
            }
            
        } catch (error) {
            this.hidePermissionDialog();
            throw error;
        }
    }

    // Request both audio and video with fallback
    async requestBothMediaTypes(constraints) {
        try {
            console.log('Requesting both audio and video permissions...');
            this.localStream = await navigator.mediaDevices.getUserMedia(constraints);
            console.log('Successfully got both audio and video stream');
            
            this.hidePermissionDialog();
            this.setupStreamHandlers();
            this.notifyStreamUpdate();
            
            return true;
        } catch (error) {
            console.warn('Failed to get both audio and video, trying with lower constraints:', error);
            
            if (error.name === 'NotAllowedError') {
                this.hidePermissionDialog();
                this.showPermissionDeniedDialog();
                throw new Error('Camera and microphone access denied. Please click the camera icon in your browser\'s address bar and allow access, then refresh the page.');
            } else if (error.name === 'OverconstrainedError') {
                return await this.tryWithLowerConstraints();
            } else {
                // Try audio with mock video as fallback
                return await this.requestAudioWithMockVideo();
            }
        }
    }

    // Request audio with mock video as fallback
    async requestAudioWithMockVideo() {
        try {
            console.log('Requesting audio and creating mock video...');
            
            // First try to get audio
            const audioStream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }, 
                video: false 
            });
            
            // Create a mock video track (black canvas)
            const mockVideoTrack = this.createMockVideoTrack();
            
            // Combine audio and mock video into a single stream
            this.localStream = new MediaStream();
            
            // Add audio tracks
            audioStream.getAudioTracks().forEach(track => {
                this.localStream.addTrack(track);
            });
            
            // Add mock video track
            if (mockVideoTrack) {
                this.localStream.addTrack(mockVideoTrack);
                this.hasMockVideo = true;
            }
            
            console.log('Successfully created audio stream with mock video');
            
            this.hidePermissionDialog();
            this.showMockVideoWarning();
            this.setupStreamHandlers();
            this.notifyStreamUpdate();
            
            return true;
        } catch (error) {
            if (error.name === 'NotAllowedError') {
                this.hidePermissionDialog();
                this.showPermissionDeniedDialog();
                throw new Error('Microphone access denied. Please allow microphone access in your browser settings and refresh the page.');
            } else {
                // Last resort: create completely mock stream
                return await this.createCompletelyMockStream();
            }
        }
    }

    // Create a mock video track (black canvas)
    createMockVideoTrack() {
        try {
            // Create a canvas element
            const canvas = document.createElement('canvas');
            canvas.width = 640;
            canvas.height = 480;
            
            // Store canvas reference for updates
            this.mockVideoCanvas = canvas;
            
            // Get canvas context and fill with black
            const ctx = canvas.getContext('2d');
            this.updateMockVideoCanvas(true); // Initialize with enabled state
            
            // Create a video track from the canvas with animation
            const stream = canvas.captureStream(15); // 15 FPS
            const videoTrack = stream.getVideoTracks()[0];
            
            // Set up periodic updates to keep the stream "alive"
            if (videoTrack) {
                this.mockVideoUpdateInterval = setInterval(() => {
                    if (this.mockVideoCanvas && this.isVideoEnabled) {
                        // Add subtle animation to prevent stream from being considered "static"
                        const time = Date.now() / 1000;
                        const alpha = (Math.sin(time * 2) + 1) / 2 * 0.1 + 0.9; // Subtle opacity change
                        
                        ctx.save();
                        ctx.globalAlpha = alpha;
                        this.updateMockVideoCanvas(this.isVideoEnabled);
                        ctx.restore();
                    }
                }, 1000 / 15); // 15 FPS
                
                // Clean up interval when track ends
                videoTrack.onended = () => {
                    if (this.mockVideoUpdateInterval) {
                        clearInterval(this.mockVideoUpdateInterval);
                        this.mockVideoUpdateInterval = null;
                    }
                };
            }
            
            return videoTrack;
        } catch (error) {
            console.error('Error creating mock video track:', error);
            return null;
        }
    }

    // Create completely mock stream as last resort
    async createCompletelyMockStream() {
        try {
            console.log('Creating completely mock stream...');
            
            // Create mock video track
            const mockVideoTrack = this.createMockVideoTrack();
            
            if (!mockVideoTrack) {
                throw new Error('Cannot create mock video track');
            }
            
            // Create a mock audio track (silent)
            const mockAudioTrack = this.createMockAudioTrack();
            
            // Create stream with mock tracks
            this.localStream = new MediaStream();
            
            if (mockAudioTrack) {
                this.localStream.addTrack(mockAudioTrack);
            }
            
            this.localStream.addTrack(mockVideoTrack);
            this.hasMockVideo = true;
            this.hasMockAudio = !!mockAudioTrack;
            
            console.log('Successfully created completely mock stream');
            
            this.hidePermissionDialog();
            this.showNoMediaDevicesWarning();
            this.setupStreamHandlers();
            this.notifyStreamUpdate();
            
            return true;
        } catch (error) {
            console.error('Error creating mock stream:', error);
            this.handleError(new Error('Unable to initialize media. Please check your browser settings and device connections.'));
            return false;
        }
    }

    // Create a mock audio track (silent)
    createMockAudioTrack() {
        try {
            // Create an audio context
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            
            // Create an oscillator with very low volume (essentially silent)
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();
            
            oscillator.connect(gainNode);
            gainNode.gain.value = 0.001; // Very low volume
            oscillator.frequency.value = 440; // A4 note
            oscillator.type = 'sine';
            
            // Create a destination for the stream
            const destination = audioContext.createMediaStreamDestination();
            gainNode.connect(destination);
            
            oscillator.start();
            
            return destination.stream.getAudioTracks()[0];
        } catch (error) {
            console.error('Error creating mock audio track:', error);
            return null;
        }
    }

    // Show mock video warning
    showMockVideoWarning() {
        this.showMediaWarning(
            'Audio Only Mode', 
            'Camera not available. Using audio-only mode with placeholder video.', 
            'fas fa-microphone text-yellow-500'
        );
    }

    // Show no media devices warning
    showNoMediaDevicesWarning() {
        this.showMediaWarning(
            'No Media Devices', 
            'Camera and microphone not available. Using placeholder media for session.', 
            'fas fa-exclamation-triangle text-red-500'
        );
    }

    // Request audio only
    async requestAudioOnly() {
        try {
            console.log('Requesting audio-only permission...');
            this.localStream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }, 
                video: false 
            });
            console.log('Successfully got audio-only stream');
            
            this.hidePermissionDialog();
            this.showAudioOnlyWarning();
            this.setupStreamHandlers();
            this.notifyStreamUpdate();
            
            return true;
        } catch (error) {
            if (error.name === 'NotAllowedError') {
                this.hidePermissionDialog();
                this.showPermissionDeniedDialog();
                throw new Error('Microphone access denied. Please allow microphone access in your browser settings and refresh the page.');
            } else {
                // Try creating mock stream as fallback
                return await this.requestAudioWithMockVideo();
            }
        }
    }

    // Request video only (fallback case)
    async requestVideoOnly() {
        try {
            console.log('Requesting video-only permission...');
            this.localStream = await navigator.mediaDevices.getUserMedia({ 
                audio: false, 
                video: {
                    width: { ideal: 1280, min: 640 },
                    height: { ideal: 720, min: 480 },
                    facingMode: "user"
                }
            });
            console.log('Successfully got video-only stream');
            
            this.hidePermissionDialog();
            this.showVideoOnlyWarning();
            this.setupStreamHandlers();
            this.notifyStreamUpdate();
            
            return true;
        } catch (error) {
            if (error.name === 'NotAllowedError') {
                this.hidePermissionDialog();
                this.showPermissionDeniedDialog();
                throw new Error('Camera access denied. Please allow camera access in your browser settings and refresh the page.');
            } else {
                throw new Error('Could not access camera: ' + error.message);
            }
        }
    }

    // Setup stream event handlers
    setupStreamHandlers() {
        if (this.localStream) {
            this.localStream.getTracks().forEach(track => {
                track.onended = () => {
                    console.log(`${track.kind} track ended`);
                    this.handleMediaTrackEnded(track);
                };
                
                track.onmute = () => {
                    console.log(`${track.kind} track muted`);
                    this.handleMediaTrackMuted(track);
                };
                
                track.onunmute = () => {
                    console.log(`${track.kind} track unmuted`);
                    this.handleMediaTrackUnmuted(track);
                };
            });
        }
    }

    // Notify about stream update
    notifyStreamUpdate() {
        if (this.onLocalStreamUpdate && this.localStream) {
            this.onLocalStreamUpdate(this.localStream);
        }
    }

    // Show permission request dialog
    showPermissionDialog(message, isError = false) {
        // Remove any existing dialog
        this.hidePermissionDialog();
        
        const dialog = document.createElement('div');
        dialog.id = 'media-permission-dialog';
        dialog.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
        
        const className = isError ? 'bg-red-50 border-red-200' : 'bg-blue-50 border-blue-200';
        const iconClass = isError ? 'fas fa-exclamation-triangle text-red-500' : 'fas fa-video text-blue-500';
        
        dialog.innerHTML = `
            <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4 shadow-xl">
                <div class="flex items-center mb-4">
                    <div class="flex-shrink-0 w-10 h-10 ${className} rounded-full flex items-center justify-center mr-3">
                        <i class="${iconClass}"></i>
                    </div>
                    <h3 class="text-lg font-semibold text-gray-900">
                        ${isError ? 'Connection Issue' : 'Camera & Microphone Access'}
                    </h3>
                </div>
                <div class="text-gray-700 mb-4">${message}</div>
                ${!isError ? '<div class="flex justify-center"><div class="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"></div></div>' : 
                '<div class="flex justify-end space-x-3 mt-4"><button onclick="this.closest(\'div[class*=\"fixed inset-0\"]\').remove()" class="px-4 py-2 bg-gray-200 text-gray-800 rounded hover:bg-gray-300">Continue Anyway</button></div>'}
            </div>
        `;
        
        document.body.appendChild(dialog);
    }

    // Hide permission dialog
    hidePermissionDialog() {
        const dialog = document.getElementById('media-permission-dialog');
        if (dialog) {
            dialog.remove();
        }
    }

    // Show permission denied dialog with instructions
    showPermissionDeniedDialog() {
        const dialog = document.createElement('div');
        dialog.id = 'permission-denied-dialog';
        dialog.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
        
        dialog.innerHTML = `
            <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4 shadow-xl">
                <div class="flex items-center mb-4">
                    <div class="flex-shrink-0 w-10 h-10 bg-red-50 border-red-200 rounded-full flex items-center justify-center mr-3">
                        <i class="fas fa-exclamation-circle text-red-500"></i>
                    </div>
                    <h3 class="text-lg font-semibold text-gray-900">Permission Required</h3>
                </div>
                <p class="text-gray-700 mb-4">
                    Camera and microphone access was denied. To join the video session, please:
                </p>
                <ol class="list-decimal list-inside text-sm text-gray-600 mb-6 space-y-1">
                    <li>Click the camera icon in your browser's address bar</li>
                    <li>Select "Allow" for both camera and microphone</li>
                    <li>Click "Try Again" below</li>
                </ol>
                <div class="flex justify-end space-x-3">
                    <button onclick="window.location.reload()" class="px-4 py-2 bg-gray-200 text-gray-800 rounded hover:bg-gray-300">
                        Refresh Page
                    </button>
                    <button onclick="this.closest('#permission-denied-dialog').remove(); if(window.retryMediaAccess) window.retryMediaAccess();" class="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600">
                        Try Again
                    </button>
                    <button onclick="this.closest('#permission-denied-dialog').remove()" class="px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600">
                        Continue Anyway
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(dialog);
    }

    // Show audio-only warning
    showAudioOnlyWarning() {
        this.showMediaWarning('Audio Only', 'Video camera could not be accessed. You can still participate with audio only.', 'fas fa-microphone text-yellow-500');
    }

    // Show video-only warning
    showVideoOnlyWarning() {
        this.showMediaWarning('Video Only', 'Microphone could not be accessed. You can still participate with video only.', 'fas fa-video text-yellow-500');
    }

    // Show media warning helper
    showMediaWarning(title, message, iconClass) {
        const warning = document.createElement('div');
        warning.className = 'fixed top-4 right-4 bg-yellow-50 border border-yellow-200 rounded-lg p-4 shadow-lg z-40 max-w-sm';
        warning.innerHTML = `
            <div class="flex items-start">
                <div class="flex-shrink-0">
                    <i class="${iconClass}"></i>
                </div>
                <div class="ml-3">
                    <h4 class="text-sm font-medium text-yellow-800">${title}</h4>
                    <p class="mt-1 text-sm text-yellow-700">${message}</p>
                </div>
                <button onclick="this.parentElement.parentElement.remove()" class="ml-auto text-yellow-500 hover:text-yellow-700">
                    <i class="fas fa-times text-sm"></i>
                </button>
            </div>
        `;
        
        document.body.appendChild(warning);
        
        // Auto-remove after 10 seconds
        setTimeout(() => {
            if (warning.parentElement) {
                warning.remove();
            }
        }, 10000);
    }

    // Handle media track muted
    handleMediaTrackMuted(track) {
        console.log(`${track.kind} track muted`);
        if (this.onDeviceChange) {
            this.onDeviceChange(`${track.kind}_muted`);
        }
    }

    // Retry media access (can be called by user action)
    async retryMediaAccess() {
        try {
            console.log('Retrying media access...');
            this.hidePermissionDialog();
            
            // Stop any existing streams first
            this.stopLocalMedia();
            
            // Try to setup media again
            const result = await this.setupLocalMedia();
            
            if (result) {
                this.updateStatus('Media devices connected successfully');
                return true;
            } else {
                this.updateStatus('Media access failed');
                return false;
            }
        } catch (error) {
            console.error('Error retrying media access:', error);
            this.handleError(error);
            return false;
        }
    }

    // Add method to manually trigger permission request
    async requestPermissions() {
        return await this.retryMediaAccess();
    }
    
    // Try with progressively lower constraints
    async tryWithLowerConstraints() {
        try {
            console.log('Trying with lower video constraints...');
            
            // Try with lower resolution
            const lowerConstraints = {
                audio: true,
                video: {
                    width: { ideal: 640, min: 320 },
                    height: { ideal: 480, min: 240 }
                }
            };
            
            this.localStream = await navigator.mediaDevices.getUserMedia(lowerConstraints);
            console.log('Got local stream with lower constraints');
            
            // Set up track ended event listeners
            this.localStream.getTracks().forEach(track => {
                track.onended = () => {
                    console.log(`${track.kind} track ended`);
                    this.handleMediaTrackEnded(track);
                };
            });
            
            // Notify about local stream
            if (this.onLocalStreamUpdate) {
                this.onLocalStreamUpdate(this.localStream);
            }
            
            return true;
        } catch (error) {
            // Try audio only as last resort
            console.log('Trying audio only...');
            try {
                this.localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
                console.log('Got audio-only local stream');
                
                // Set up track ended event listeners
                this.localStream.getTracks().forEach(track => {
                    track.onended = () => {
                        console.log(`${track.kind} track ended`);
                        this.handleMediaTrackEnded(track);
                    };
                });
                
                // Notify about local stream
                if (this.onLocalStreamUpdate) {
                    this.onLocalStreamUpdate(this.localStream);
                }
                
                return true;
            } catch (finalError) {
                console.error('Failed to get media even with audio only:', finalError);
                this.handleError(new Error('Could not access any media devices. Please check your hardware and permissions.'));
                return false;
            }
        }
    }
    
    // Handle media track ended event
    handleMediaTrackEnded(track) {
        // Notify user that a device was disconnected
        const message = `Your ${track.kind} device was disconnected`;
        this.updateStatus(message);
        
        // Try to recover if possible
        if (this.localStream && this.isConnected) {
            // For now just notify, but could try to reacquire the track
            this.handleError(new Error(message));
        }
    }

    // Stop local media
    stopLocalMedia() {
        if (this.localStream) {
            console.log('Stopping local media...');
            
            this.localStream.getTracks().forEach(track => {
                track.stop();
            });
            
            this.localStream = null;
        }
        
        // Clean up mock video resources
        if (this.mockVideoUpdateInterval) {
            clearInterval(this.mockVideoUpdateInterval);
            this.mockVideoUpdateInterval = null;
        }
        
        this.mockVideoCanvas = null;
        this.hasMockVideo = false;
        this.hasMockAudio = false;
        
        if (this.screenStream) {
            console.log('Stopping screen sharing...');
            
            this.screenStream.getTracks().forEach(track => {
                track.stop();
            });
            
            this.screenStream = null;
            this.isScreenSharing = false;
        }
    }

    // Create peer connection
    createPeerConnection() {
        if (this.peerConnection) {
            console.log('Peer connection already exists');
            return this.peerConnection;
        }
        
        try {
            console.log('Creating peer connection...');
            
            // Check for WebRTC support
            if (!window.RTCPeerConnection) {
                throw new Error('WebRTC is not supported in your browser');
            }
            
            this.peerConnection = new RTCPeerConnection(this.peerConnectionConfig);
            
            // Set up event handlers
            this.peerConnection.onicecandidate = this.handleIceCandidate.bind(this);
            this.peerConnection.ontrack = this.handleTrack.bind(this);
            this.peerConnection.oniceconnectionstatechange = this.handleIceConnectionStateChange.bind(this);
            this.peerConnection.onconnectionstatechange = this.handleConnectionStateChange.bind(this);
            
            // Add local stream tracks to peer connection if available
            this.addLocalTracksToConnection();
            
            console.log('Peer connection created');
            return this.peerConnection;
        } catch (error) {
            console.error('Error creating peer connection:', error);
            this.handleError(error);
            return null;
        }
    }
    
    // Add local tracks to peer connection
    addLocalTracksToConnection() {
        if (!this.peerConnection) {
            console.error('Cannot add tracks: peer connection not created');
            return false;
        }
        
        if (!this.localStream) {
            console.warn('Cannot add tracks: local stream not available');
            return false;
        }
        
        const tracks = this.localStream.getTracks();
        if (tracks.length === 0) {
            console.warn('No tracks found in local stream');
            return false;
        }
        
        console.log(`Adding ${tracks.length} tracks to peer connection`);
        tracks.forEach(track => {
            this.peerConnection.addTrack(track, this.localStream);
        });
        
        return true;
    }
    
    // Handle connection state change
    handleConnectionStateChange() {
        if (!this.peerConnection) return;
        
        console.log('Connection state:', this.peerConnection.connectionState);
        
        switch (this.peerConnection.connectionState) {
            case 'connected':
                this.updateStatus('Connected');
                break;
            case 'disconnected':
                this.updateStatus('Connection interrupted');
                this.attemptReconnection();
                break;
            case 'failed':
                this.updateStatus('Connection failed');
                this.handleError(new Error('Connection failed'));
                this.attemptReconnection();
                break;
            case 'closed':
                this.updateStatus('Connection closed');
                break;
        }
    }
    
    // Attempt to reconnect after connection failure
    attemptReconnection() {
        if (this.reconnectionAttempts >= 3) {
            console.log('Maximum reconnection attempts reached');
            return;
        }
        
        this.reconnectionAttempts = (this.reconnectionAttempts || 0) + 1;
        console.log(`Attempting reconnection (${this.reconnectionAttempts}/3)...`);
        
        // Wait a bit before trying to reconnect
        setTimeout(() => {
            if (this.peerConnection && 
                (this.peerConnection.iceConnectionState === 'disconnected' || 
                 this.peerConnection.iceConnectionState === 'failed')) {
                
                // Close the old connection
                this.closePeerConnection();
                
                // Create a new connection
                this.createPeerConnection();
                
                // Reinitiate the call if we're the initiator
                if (this.role === 'counselor' && this.otherParticipant) {
                    this.initiateCall();
                }
            }
        }, 2000);
    }

    // Close peer connection
    closePeerConnection() {
        if (this.peerConnection) {
            console.log('Closing peer connection...');
            
            this.peerConnection.close();
            this.peerConnection = null;
            
            // Clear remote stream
            if (this.remoteStream) {
                this.remoteStream = null;
                
                // Notify about remote stream update
                if (this.onRemoteStreamUpdate) {
                    this.onRemoteStreamUpdate(null);
                }
            }
        }
    }

    // Initiate call (create and send offer)
    async initiateCall() {
        if (!this.peerConnection) {
            console.error('Cannot initiate call: peer connection not created');
            return;
        }
        
        if (!this.otherParticipant) {
            console.error('Cannot initiate call: no other participant');
            return;
        }
        
        try {
            console.log('Initiating call...');
            
            const offer = await this.peerConnection.createOffer();
            await this.peerConnection.setLocalDescription(offer);
            console.log('Created and set local description (offer)');
            
            this.socket.emit('offer', {
                target: this.otherParticipant.user_id,
                session_id: this.sessionId,
                offer: offer
            });
        } catch (error) {
            console.error('Error initiating call:', error);
            this.handleError(error);
        }
    }

    // Handle ICE candidate event
    handleIceCandidate(event) {
        if (event.candidate && this.otherParticipant) {
            console.log('ICE candidate generated');
            
            // Check if remote description is set before sending candidates
            if (this.peerConnection.currentRemoteDescription) {
                console.log('Sending ICE candidate');
                this.socket.emit('ice_candidate', {
                    target: this.otherParticipant.user_id,
                    session_id: this.sessionId,
                    candidate: event.candidate
                });
            } else {
                // Store candidates to send later
                if (!this.pendingIceCandidates) {
                    this.pendingIceCandidates = [];
                }
                
                console.log('Remote description not set yet, storing ICE candidate');
                this.pendingIceCandidates.push(event.candidate);
            }
        } else if (!event.candidate) {
            console.log('ICE candidate gathering completed');
        }
    }
    
    // Send any pending ICE candidates
    sendPendingIceCandidates() {
        if (this.pendingIceCandidates && this.pendingIceCandidates.length > 0 && 
            this.peerConnection && this.peerConnection.currentRemoteDescription && 
            this.otherParticipant) {
            
            console.log(`Sending ${this.pendingIceCandidates.length} stored ICE candidates`);
            
            this.pendingIceCandidates.forEach(candidate => {
                this.socket.emit('ice_candidate', {
                    target: this.otherParticipant.user_id,
                    session_id: this.sessionId,
                    candidate: candidate
                });
            });
            
            // Clear pending candidates
            this.pendingIceCandidates = [];
        }
    }

    // Handle track event
    handleTrack(event) {
        console.log(`Received remote ${event.track.kind} track`);
        
        if (!this.remoteStream) {
            this.remoteStream = new MediaStream();
            
            // Notify about remote stream update
            if (this.onRemoteStreamUpdate) {
                this.onRemoteStreamUpdate(this.remoteStream);
            }
        }
        
        // Check if we already have a track of this kind
        const existingTrack = this.remoteStream.getTracks().find(track => track.kind === event.track.kind);
        if (existingTrack) {
            console.log(`Replacing existing ${event.track.kind} track`);
            this.remoteStream.removeTrack(existingTrack);
        }
        
        // Add track to remote stream
        this.remoteStream.addTrack(event.track);
        
        // Set up ended event handler
        event.track.onended = () => {
            console.log(`Remote ${event.track.kind} track ended`);
            
            // Remove the track from the stream
            this.remoteStream.removeTrack(event.track);
            
            // Notify about track ended
            this.updateStatus(`Remote ${event.track.kind === 'audio' ? 'microphone' : 'camera'} disconnected`);
        };
        
        // Set up muted event handler
        event.track.onmute = () => {
            console.log(`Remote ${event.track.kind} track muted`);
            this.updateStatus(`Remote ${event.track.kind === 'audio' ? 'microphone' : 'camera'} muted`);
        };
        
        // Set up unmuted event handler
        event.track.onunmute = () => {
            console.log(`Remote ${event.track.kind} track unmuted`);
            this.updateStatus(`Remote ${event.track.kind === 'audio' ? 'microphone' : 'camera'} unmuted`);
        };
        
        // Update status based on track kind
        if (event.track.kind === 'video') {
            this.updateStatus('Remote video connected');
        } else if (event.track.kind === 'audio') {
            this.updateStatus('Remote audio connected');
        }
    }

    // Handle ICE connection state change
    handleIceConnectionStateChange() {
        console.log('ICE connection state:', this.peerConnection.iceConnectionState);
        
        switch (this.peerConnection.iceConnectionState) {
            case 'connected':
            case 'completed':
                this.updateStatus('Connected');
                break;
            case 'disconnected':
                this.updateStatus('Connection interrupted');
                break;
            case 'failed':
                this.updateStatus('Connection failed');
                this.handleError(new Error('ICE connection failed'));
                break;
            case 'closed':
                this.updateStatus('Connection closed');
                break;
        }
    }

    // Toggle audio with improved error handling and mock audio support
    toggleAudio() {
        if (!this.localStream) {
            console.error('Cannot toggle audio: no local stream available');
            this.showNoMediaDialog('microphone');
            return false;
        }
        
        const audioTrack = this.localStream.getAudioTracks()[0];
        if (!audioTrack) {
            console.log('No audio track available, attempting to add mock audio...');
            
            // Try to add a mock audio track
            if (this.addMockAudioTrack()) {
                this.isAudioEnabled = true;
                this.hasMockAudio = true;
                
                // Notify server about audio state change
                if (this.socket && this.socket.connected) {
                    this.socket.emit('toggle_audio', {
                        session_id: this.sessionId,
                        enabled: this.isAudioEnabled
                    });
                }
                
                // Notify UI callback
                if (this.onAudioStateChanged) {
                    this.onAudioStateChanged({
                        user_id: this.currentUserId || 'local',
                        enabled: this.isAudioEnabled
                    });
                }
                
                this.showMockAudioAddedNotification();
                return true;
            } else {
                this.showNoMediaDialog('microphone');
                return false;
            }
        }
        
        // Toggle existing audio track
        this.isAudioEnabled = !this.isAudioEnabled;
        audioTrack.enabled = this.isAudioEnabled;
        console.log('Audio enabled:', this.isAudioEnabled);
        
        // Notify server about audio state change
        if (this.socket && this.socket.connected) {
            this.socket.emit('toggle_audio', {
                session_id: this.sessionId,
                enabled: this.isAudioEnabled
            });
        }
        
        // Notify UI callback if available
        if (this.onAudioStateChanged) {
            this.onAudioStateChanged({
                user_id: this.currentUserId || 'local',
                enabled: this.isAudioEnabled
            });
        }
        
        return this.isAudioEnabled;
    }

    // Add mock audio track to existing stream
    addMockAudioTrack() {
        try {
            const mockAudioTrack = this.createMockAudioTrack();
            if (mockAudioTrack) {
                this.localStream.addTrack(mockAudioTrack);
                this.hasMockAudio = true;
                
                // Update the peer connection if it exists
                if (this.peerConnection) {
                    this.peerConnection.addTrack(mockAudioTrack, this.localStream);
                }
                
                // Notify about stream update
                this.notifyStreamUpdate();
                
                return true;
            }
            return false;
        } catch (error) {
            console.error('Error adding mock audio track:', error);
            return false;
        }
    }

    // Show notification when mock audio is added
    showMockAudioAddedNotification() {
        const notification = document.createElement('div');
        notification.className = 'fixed top-4 right-4 bg-blue-50 border border-blue-200 rounded-lg p-4 shadow-lg z-40 max-w-sm';
        notification.innerHTML = `
            <div class="flex items-start">
                <div class="flex-shrink-0">
                    <i class="fas fa-microphone text-blue-500"></i>
                </div>
                <div class="ml-3">
                    <h4 class="text-sm font-medium text-blue-800">Audio Enabled</h4>
                    <p class="mt-1 text-sm text-blue-700">Using silent audio track since no microphone is available.</p>
                </div>
                <button onclick="this.parentElement.parentElement.remove()" class="ml-auto text-blue-500 hover:text-blue-700">
                    <i class="fas fa-times text-sm"></i>
                </button>
            </div>
        `;
        
        document.body.appendChild(notification);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentElement) {
                notification.remove();
            }
        }, 5000);
    }

    // Toggle video with improved error handling and mock video support
    toggleVideo() {
        if (!this.localStream) {
            console.error('Cannot toggle video: no local stream available');
            this.showNoMediaDialog('camera');
            return false;
        }
        
        const videoTrack = this.localStream.getVideoTracks()[0];
        if (!videoTrack) {
            console.log('No video track available, attempting to add mock video...');
            
            // Try to add a mock video track
            if (this.addMockVideoTrack()) {
                this.isVideoEnabled = true;
                this.hasMockVideo = true;
                
                // Notify server about video state change
                if (this.socket && this.socket.connected) {
                    this.socket.emit('toggle_video', {
                        session_id: this.sessionId,
                        enabled: this.isVideoEnabled
                    });
                }
                
                // Notify UI callback
                if (this.onVideoStateChanged) {
                    this.onVideoStateChanged({
                        user_id: this.currentUserId || 'local',
                        enabled: this.isVideoEnabled
                    });
                }
                
                this.showMockVideoAddedNotification();
                return true;
            } else {
                this.showNoMediaDialog('camera');
                return false;
            }
        }
        
        // Toggle existing video track
        this.isVideoEnabled = !this.isVideoEnabled;
        videoTrack.enabled = this.isVideoEnabled;
        console.log('Video enabled:', this.isVideoEnabled);
        
        // Update mock video canvas if needed
        if (this.hasMockVideo && this.mockVideoCanvas) {
            this.updateMockVideoCanvas(this.isVideoEnabled);
        }
        
        // Notify server about video state change
        if (this.socket && this.socket.connected) {
            this.socket.emit('toggle_video', {
                session_id: this.sessionId,
                enabled: this.isVideoEnabled
            });
        }
        
        // Notify UI callback if available
        if (this.onVideoStateChanged) {
            this.onVideoStateChanged({
                user_id: this.currentUserId || 'local',
                enabled: this.isVideoEnabled
            });
        }
        
        return this.isVideoEnabled;
    }

    // Add mock video track to existing stream
    addMockVideoTrack() {
        try {
            const mockVideoTrack = this.createMockVideoTrack();
            if (mockVideoTrack) {
                this.localStream.addTrack(mockVideoTrack);
                this.hasMockVideo = true;
                
                // Update the peer connection if it exists
                if (this.peerConnection) {
                    this.peerConnection.addTrack(mockVideoTrack, this.localStream);
                }
                
                // Notify about stream update
                this.notifyStreamUpdate();
                
                return true;
            }
            return false;
        } catch (error) {
            console.error('Error adding mock video track:', error);
            return false;
        }
    }

    // Update mock video canvas content
    updateMockVideoCanvas(isEnabled) {
        if (!this.mockVideoCanvas) return;
        
        const ctx = this.mockVideoCanvas.getContext('2d');
        
        if (isEnabled) {
            // Show "Camera Not Available" message
            ctx.fillStyle = '#000000';
            ctx.fillRect(0, 0, this.mockVideoCanvas.width, this.mockVideoCanvas.height);
            
            ctx.fillStyle = '#FFFFFF';
            ctx.font = '24px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('Camera Not Available', this.mockVideoCanvas.width / 2, this.mockVideoCanvas.height / 2 - 20);
            ctx.font = '16px Arial';
            ctx.fillText('Audio Only', this.mockVideoCanvas.width / 2, this.mockVideoCanvas.height / 2 + 20);
        } else {
            // Show "Video Disabled" message
            ctx.fillStyle = '#333333';
            ctx.fillRect(0, 0, this.mockVideoCanvas.width, this.mockVideoCanvas.height);
            
            ctx.fillStyle = '#888888';
            ctx.font = '24px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('Video Disabled', this.mockVideoCanvas.width / 2, this.mockVideoCanvas.height / 2 - 10);
            ctx.font = '16px Arial';
            ctx.fillText('Click to enable', this.mockVideoCanvas.width / 2, this.mockVideoCanvas.height / 2 + 20);
        }
    }

    // Show notification when mock video is added
    showMockVideoAddedNotification() {
        const notification = document.createElement('div');
        notification.className = 'fixed top-4 right-4 bg-green-50 border border-green-200 rounded-lg p-4 shadow-lg z-40 max-w-sm';
        notification.innerHTML = `
            <div class="flex items-start">
                <div class="flex-shrink-0">
                    <i class="fas fa-video text-green-500"></i>
                </div>
                <div class="ml-3">
                    <h4 class="text-sm font-medium text-green-800">Video Enabled</h4>
                    <p class="mt-1 text-sm text-green-700">Using placeholder video since no camera is available.</p>
                </div>
                <button onclick="this.parentElement.parentElement.remove()" class="ml-auto text-green-500 hover:text-green-700">
                    <i class="fas fa-times text-sm"></i>
                </button>
            </div>
        `;
        
        document.body.appendChild(notification);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentElement) {
                notification.remove();
            }
        }, 5000);
    }

    // Show dialog when media is not available
    showNoMediaDialog(deviceType) {
        const dialog = document.createElement('div');
        dialog.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
        
        const deviceName = deviceType === 'camera' ? 'Camera' : 'Microphone';
        const icon = deviceType === 'camera' ? 'fas fa-video-slash' : 'fas fa-microphone-slash';
        
        dialog.innerHTML = `
            <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4 shadow-xl">
                <div class="flex items-center mb-4">
                    <div class="flex-shrink-0 w-10 h-10 bg-red-50 border-red-200 rounded-full flex items-center justify-center mr-3">
                        <i class="${icon} text-red-500"></i>
                    </div>
                    <h3 class="text-lg font-semibold text-gray-900">${deviceName} Not Available</h3>
                </div>
                <p class="text-gray-700 mb-4">
                    Your ${deviceType} is not available. This could be because:
                </p>
                <ul class="list-disc list-inside text-sm text-gray-600 mb-6 space-y-1">
                    <li>Permission was not granted</li>
                    <li>The device is being used by another application</li>
                    <li>The device is not connected</li>
                    <li>Your browser requires HTTPS for media access</li>
                </ul>
                <div class="flex justify-end space-x-3">
                    <button onclick="this.closest('div[class*=\"fixed inset-0\"]').remove()" class="px-4 py-2 bg-gray-200 text-gray-800 rounded hover:bg-gray-300">
                        Continue
                    </button>
                    <button onclick="this.closest('div[class*=\"fixed inset-0\"]').remove(); if(window.retryMediaAccess) window.retryMediaAccess();" class="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600">
                        Try Again
                    </button>
                    <button onclick="window.location.reload()" class="px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600">
                        Refresh Page
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(dialog);
        
        // Auto-remove after 15 seconds instead of 10
        setTimeout(() => {
            if (dialog.parentElement) {
                dialog.remove();
            }
        }, 15000);
    }

    // Toggle screen sharing
    async toggleScreenSharing() {
        if (!this.peerConnection) {
            console.error('Cannot toggle screen sharing: peer connection not created');
            return false;
        }
        
        try {
            if (!this.isScreenSharing) {
                // Start screen sharing
                this.screenStream = await navigator.mediaDevices.getDisplayMedia({
                    video: true,
                    audio: false
                });
                
                // Replace video track with screen track
                const videoSender = this.peerConnection.getSenders().find(sender => 
                    sender.track && sender.track.kind === 'video'
                );
                
                if (videoSender) {
                    const screenTrack = this.screenStream.getVideoTracks()[0];
                    await videoSender.replaceTrack(screenTrack);
                    
                    // Update local stream for UI
                    if (this.onLocalStreamUpdate) {
                        const combinedStream = new MediaStream();
                        
                        // Add audio track from original stream
                        this.localStream.getAudioTracks().forEach(track => {
                            combinedStream.addTrack(track);
                        });
                        
                        // Add video track from screen stream
                        combinedStream.addTrack(screenTrack);
                        
                        this.onLocalStreamUpdate(combinedStream);
                    }
                    
                    // Handle screen sharing ended by user
                    screenTrack.onended = () => {
                        this.toggleScreenSharing();
                    };
                    
                    this.isScreenSharing = true;
                    console.log('Screen sharing started');
                }
            } else {
                // Stop screen sharing
                if (this.screenStream) {
                    this.screenStream.getTracks().forEach(track => {
                        track.stop();
                    });
                }
                
                // Replace screen track with video track
                const videoSender = this.peerConnection.getSenders().find(sender => 
                    sender.track && sender.track.kind === 'video'
                );
                
                if (videoSender && this.localStream) {
                    const videoTrack = this.localStream.getVideoTracks()[0];
                    if (videoTrack) {
                        await videoSender.replaceTrack(videoTrack);
                        
                        // Update local stream for UI
                        if (this.onLocalStreamUpdate) {
                            this.onLocalStreamUpdate(this.localStream);
                        }
                    }
                }
                
                this.screenStream = null;
                this.isScreenSharing = false;
                console.log('Screen sharing stopped');
            }
            
            return this.isScreenSharing;
        } catch (error) {
            console.error('Error toggling screen sharing:', error);
            this.handleError(error);
            return false;
        }
    }

    // Send chat message
    sendChatMessage(message) {
        if (!this.isConnected) {
            console.error('Cannot send message: not connected to server');
            return false;
        }
        
        if (!message || !message.trim()) {
            console.error('Cannot send empty message');
            return false;
        }
        
        console.log('Sending chat message:', message);
        this.socket.emit('chat_message', {
            session_id: this.sessionId,
            message: message
        });
        
        return true;
    }

    // Update status
    updateStatus(status) {
        console.log('Status:', status);
        
        if (this.onStatusChange) {
            this.onStatusChange(status);
        }
    }

    // Handle error
    handleError(error) {
        console.error('Error:', error);
        
        // Create user-friendly error message
        let userMessage = 'An error occurred';
        
        // Handle specific WebRTC errors
        if (error.name) {
            switch (error.name) {
                case 'NotAllowedError':
                    userMessage = 'Camera/microphone access denied. Please allow access in your browser settings.';
                    break;
                case 'NotFoundError':
                    userMessage = 'Camera or microphone not found. Please check your device connections.';
                    break;
                case 'NotReadableError':
                    userMessage = 'Camera or microphone is already in use by another application.';
                    break;
                case 'OverconstrainedError':
                    userMessage = 'Camera does not support the requested resolution.';
                    break;
                case 'AbortError':
                    userMessage = 'Media access was aborted.';
                    break;
                case 'SecurityError':
                    userMessage = 'Media access was blocked due to security restrictions.';
                    break;
                case 'TypeError':
                    userMessage = 'Invalid media constraints specified.';
                    break;
            }
        } else if (error.message) {
            // Use the error message if available
            userMessage = error.message;
        }
        
        // Update status with user-friendly message
        this.updateStatus(userMessage);
        
        // Call error callback if available
        if (this.onError) {
            this.onError({
                originalError: error,
                message: userMessage
            });
        }
    }

    // Get status message based on waiting room status
    getStatusMessage(waitingRoomStatus) {
        switch (waitingRoomStatus) {
            case 'empty':
                return 'Waiting for participants...';
            case 'counselor_waiting':
                return 'Counselor is waiting for you to join...';
            case 'student_waiting':
                return 'Waiting for counselor to join...';
            case 'both_waiting':
                return 'Both participants present, starting call...';
            case 'call_in_progress':
                return 'Call in progress';
            default:
                return 'Unknown status';
        }
    }

    // Handle device change
    async handleDeviceChange() {
        console.log('Media devices changed');
        
        // Check if we have a callback for device changes
        if (this.onDeviceChange) {
            try {
                // Get updated device list
                const devices = await navigator.mediaDevices.enumerateDevices();
                
                // Group devices by kind
                const audioInputs = devices.filter(device => device.kind === 'audioinput');
                const videoInputs = devices.filter(device => device.kind === 'videoinput');
                const audioOutputs = devices.filter(device => device.kind === 'audiooutput');
                
                // Notify about device change
                this.onDeviceChange({
                    audioInputs,
                    videoInputs,
                    audioOutputs,
                    hasAudioInput: audioInputs.length > 0,
                    hasVideoInput: videoInputs.length > 0,
                    hasAudioOutput: audioOutputs.length > 0
                });
                
                // If we're in a call and a device was disconnected, check if it affects our stream
                if (this.localStream) {
                    const audioTrack = this.localStream.getAudioTracks()[0];
                    const videoTrack = this.localStream.getVideoTracks()[0];
                    
                    // Check if we have audio but no audio devices
                    if (audioTrack && audioTrack.readyState === 'live' && audioInputs.length === 0) {
                        this.updateStatus('Audio device disconnected');
                        audioTrack.stop();
                    }
                    
                    // Check if we have video but no video devices
                    if (videoTrack && videoTrack.readyState === 'live' && videoInputs.length === 0) {
                        this.updateStatus('Video device disconnected');
                        videoTrack.stop();
                    }
                    
                    // If we're in an active call and devices changed, we might need to update our stream
                    if (this.peerConnection && this.peerConnection.connectionState === 'connected') {
                        // For now just notify, but could implement device switching here
                        this.updateStatus('Media devices changed during active call');
                    }
                }
            } catch (error) {
                console.error('Error handling device change:', error);
            }
        }
    }
}

// Export the client class
window.VideoCounselingClient = VideoCounselingClient;