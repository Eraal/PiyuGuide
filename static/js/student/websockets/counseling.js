// Video Counseling WebSocket Client for Students
console.log("Video Counseling WebSocket Client for Students");

class VideoCounselingClient {
    constructor(sessionId, userId, userName) {
        this.sessionId = sessionId;
        this.userId = userId;
        this.userName = userName;
        this.socket = null;
        this.peerConnection = null;
        this.localStream = null;
        this.remoteStream = null;
        this.isAudioEnabled = true;
        this.isVideoEnabled = true;
        this.isConnected = false;
        this.sessionTimer = null;
        this.startTime = null;
        this.isInCall = false;
        this.heartbeatInterval = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.connectionQuality = 'unknown';
        
        // ICE servers configuration
        this.iceServers = [
            { urls: 'stun:stun.l.google.com:19302' },
            { urls: 'stun:stun1.l.google.com:19302' },
            { urls: 'stun:stun2.l.google.com:19302' }
        ];
        
        // Media constraints
        this.mediaConstraints = {
            video: {
                width: { ideal: 1280, max: 1920 },
                height: { ideal: 720, max: 1080 },
                frameRate: { ideal: 30, max: 30 }
            },
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
            }
        };
        
        this.init();
    }
    
    async init() {
        try {
            console.log('Initializing Video Counseling Client for Student...');
            this.updateConnectionStatus('Initializing...', 'info');
            this.initializeSocket();
            this.setupEventListeners();
            await this.initializeMedia();
            this.showWaitingRoom();
            // Initialize participant indicators - student is connected, counselor is not yet
            this.updateParticipantIndicators(false, true);
        } catch (error) {
            console.error('Failed to initialize video counseling:', error);
            this.updateConnectionStatus('Initialization failed', 'error');
            this.showError('Failed to initialize video calling. Please refresh and try again.');
        }
    }
    
    initializeSocket() {
        console.log('Connecting to video counseling namespace...');
        this.socket = io('/video-counseling', {
            transports: ['websocket', 'polling'],
            timeout: 20000,
            forceNew: true
        });
        
        this.setupSocketEventHandlers();
    }
    
    setupSocketEventHandlers() {
        this.socket.on('connect', () => {
            console.log('Connected to video counseling server');
            this.isConnected = true;
            this.reconnectAttempts = 0;
            this.updateConnectionStatus('Connecting to session...', 'info');
            this.joinSession();
            this.startHeartbeat();
        });
        
        this.socket.on('disconnect', () => {
            console.log('Disconnected from video counseling server');
            this.isConnected = false;
            this.updateConnectionStatus('Disconnected from server', 'error');
            this.stopHeartbeat();
            this.handleDisconnection();
        });
        
        this.socket.on('connect_error', (error) => {
            console.error('Connection error:', error);
            this.updateConnectionStatus('Connection error', 'error');
            this.handleConnectionError();
        });
        
        this.socket.on('session_joined', (data) => {
            console.log('Successfully joined session:', data);
            this.updateWaitingRoomMessage('Waiting for counselor to join...');
            
            // Check if counselor is already present
            const counselorPresent = data.participants.some(p => 
                p.role === 'office_admin' || p.role === 'super_admin'
            );
            
            if (counselorPresent) {
                this.updateWaitingRoomMessage('Counselor is present. Getting ready...');
                this.updateConnectionStatus('Counselor detected - both users present', 'success');
                this.updateParticipantIndicators(true, true);
                this.socket.emit('ready', { session_id: this.sessionId });
            } else {
                this.updateConnectionStatus('Connected - waiting for counselor', 'warning');
                this.updateParticipantIndicators(false, true);
            }
        });
        
        this.socket.on('user_joined', (data) => {
            console.log('User joined session:', data);
            if (data.role === 'office_admin' || data.role === 'super_admin') {
                this.updateWaitingRoomMessage('Counselor has joined. Getting ready...');
                this.updateConnectionStatus('Counselor joined - both users present', 'success');
                this.updateParticipantIndicators(true, true);
                this.socket.emit('ready', { session_id: this.sessionId });
            }
        });
        
        this.socket.on('user_ready', (data) => {
            console.log('User ready:', data);
            if (data.role === 'office_admin' || data.role === 'super_admin') {
                this.updateWaitingRoomMessage('Counselor is ready. Preparing call...');
                this.updateConnectionStatus('Both users ready - call can start', 'success');
            }
        });
        
        this.socket.on('session_ready', (data) => {
            console.log('Session is ready to start:', data);
            this.updateConnectionStatus('Ready to start call', 'success');
            this.showJoinCallButton();
        });
        
        this.socket.on('offer_received', async (data) => {
            console.log('Received WebRTC offer from:', data.from_name);
            try {
                await this.handleOffer(data.offer);
            } catch (error) {
                console.error('Error handling offer:', error);
                this.showError('Failed to process video call offer');
            }
        });
        
        this.socket.on('answer_received', async (data) => {
            console.log('Received WebRTC answer');
            try {
                await this.handleAnswer(data.answer);
            } catch (error) {
                console.error('Error handling answer:', error);
            }
        });
        
        this.socket.on('ice_candidate_received', async (data) => {
            try {
                await this.handleIceCandidate(data.candidate);
            } catch (error) {
                console.error('Error handling ICE candidate:', error);
            }
        });
        
        this.socket.on('user_audio_toggle', (data) => {
            this.handleRemoteAudioToggle(data);
        });
        
        this.socket.on('user_video_toggle', (data) => {
            this.handleRemoteVideoToggle(data);
        });
        
        this.socket.on('recording_started', (data) => {
            this.showRecordingIndicator(true);
            this.showNotification(`Recording started by ${data.started_by}`, 'info');
        });
        
        this.socket.on('recording_stopped', (data) => {
            this.showRecordingIndicator(false);
            this.showNotification(`Recording stopped by ${data.stopped_by}`, 'info');
        });
        
        this.socket.on('session_ended', (data) => {
            console.log('Session ended by:', data.ended_by);
            this.handleSessionEnd(data);
        });
        
        this.socket.on('user_left', (data) => {
            console.log('User left session:', data);
            if (data.role === 'office_admin' || data.role === 'super_admin') {
                this.updateConnectionStatus('Counselor disconnected', 'error');
                this.updateParticipantIndicators(false, true);
                this.handleCounselorDisconnect();
            }
        });
        
        this.socket.on('quality_update', (data) => {
            this.updateConnectionQuality(data.quality);
        });
        
        this.socket.on('error', (data) => {
            console.error('Server error:', data.message);
            this.showError(data.message);
        });
        
        this.socket.on('heartbeat_ack', () => {
            // Heartbeat acknowledged
        });
    }
    
    async initializeMedia() {
        console.log('Requesting media access...');
        this.updateConnectionStatus('Requesting camera and microphone access...', 'info');
        
        try {
            // Start with more permissive constraints to ensure compatibility
            const basicConstraints = {
                video: {
                    width: { ideal: 1280, min: 640 },
                    height: { ideal: 720, min: 480 },
                    frameRate: { ideal: 30, min: 15 }
                },
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                    sampleRate: 44100
                }
            };
            
            this.localStream = await navigator.mediaDevices.getUserMedia(basicConstraints);
            console.log('Media access granted successfully');
            
            // Verify we have both audio and video tracks
            const videoTracks = this.localStream.getVideoTracks();
            const audioTracks = this.localStream.getAudioTracks();
            
            console.log('Video tracks:', videoTracks.length);
            console.log('Audio tracks:', audioTracks.length);
            
            if (videoTracks.length === 0) {
                console.warn('No video track available');
                this.isVideoEnabled = false;
            }
            
            if (audioTracks.length === 0) {
                console.warn('No audio track available');
                this.isAudioEnabled = false;
            }
            
            // Set track states based on initial preferences
            videoTracks.forEach(track => {
                track.enabled = this.isVideoEnabled;
            });
            
            audioTracks.forEach(track => {
                track.enabled = this.isAudioEnabled;
            });
            
            // Attach to waiting room video element first
            const waitingRoomVideo = document.getElementById('waitingRoomVideo');
            if (waitingRoomVideo) {
                waitingRoomVideo.srcObject = this.localStream;
                waitingRoomVideo.muted = true;
                
                waitingRoomVideo.onloadedmetadata = () => {
                    waitingRoomVideo.play().catch(e => {
                        console.warn('Failed to play waiting room video:', e);
                    });
                };
            }
            
            // Also attach to main local video element if it exists
            const localVideo = document.getElementById('localVideo');
            if (localVideo) {
                localVideo.srcObject = this.localStream;
                localVideo.muted = true;
                
                localVideo.onloadedmetadata = () => {
                    localVideo.play().catch(e => {
                        console.warn('Failed to play local video:', e);
                    });
                };
            }
            
            // Populate device lists
            await this.populateDeviceList();
            
            // Initialize button states
            this.updateAllMediaButtons();
            this.updateVideoPlaceholder();
            
            this.updateConnectionStatus('Camera and microphone ready', 'success');
            
        } catch (error) {
            console.error('Failed to access media devices:', error);
            this.handleMediaError(error);
        }
    }
    
    async populateDeviceList() {
        try {
            const devices = await navigator.mediaDevices.enumerateDevices();
            
            const videoDevices = devices.filter(device => device.kind === 'videoinput');
            const audioDevices = devices.filter(device => device.kind === 'audioinput');
            
            // Populate camera select
            const cameraSelect = document.getElementById('cameraSelect');
            if (cameraSelect) {
                cameraSelect.innerHTML = '';
                videoDevices.forEach(device => {
                    const option = document.createElement('option');
                    option.value = device.deviceId;
                    option.textContent = device.label || `Camera ${cameraSelect.options.length + 1}`;
                    cameraSelect.appendChild(option);
                });
            }
            
            // Populate microphone select
            const micSelect = document.getElementById('microphoneSelect');
            if (micSelect) {
                micSelect.innerHTML = '';
                audioDevices.forEach(device => {
                    const option = document.createElement('option');
                    option.value = device.deviceId;
                    option.textContent = device.label || `Microphone ${micSelect.options.length + 1}`;
                    micSelect.appendChild(option);
                });
            }
            
        } catch (error) {
            console.error('Error enumerating devices:', error);
        }
    }
    
    setupEventListeners() {
        // Media control buttons (main call interface) - FIXED IDs
        const toggleAudioBtn = document.getElementById('micToggle'); // Changed from 'toggleAudioBtn'
        if (toggleAudioBtn) {
            toggleAudioBtn.addEventListener('click', () => this.toggleAudio());
        }
        
        const toggleVideoBtn = document.getElementById('cameraToggle'); // Changed from 'toggleVideoBtn'
        if (toggleVideoBtn) {
            toggleVideoBtn.addEventListener('click', () => this.toggleVideo());
        }
        
        // Waiting room media control buttons
        const waitingRoomMicToggle = document.getElementById('waitingRoomMicToggle');
        if (waitingRoomMicToggle) {
            waitingRoomMicToggle.addEventListener('click', () => this.toggleAudio(true));
        }
        
        const waitingRoomCameraToggle = document.getElementById('waitingRoomCameraToggle');
        if (waitingRoomCameraToggle) {
            waitingRoomCameraToggle.addEventListener('click', () => this.toggleVideo(true));
        }
        
        // End call button (check both possible IDs)
        const endCallBtn = document.getElementById('endCallBtn');
        if (endCallBtn) {
            endCallBtn.addEventListener('click', () => this.showEndSessionModal());
        }
        
        const endSessionBtn = document.getElementById('endSessionButton');
        if (endSessionBtn) {
            endSessionBtn.addEventListener('click', () => this.showEndSessionModal());
        }
        
        // Join call button
        const joinCallBtn = document.getElementById('joinCallBtn');
        if (joinCallBtn) {
            joinCallBtn.addEventListener('click', () => this.startCall());
        }
        
        // Fullscreen button
        const fullscreenBtn = document.getElementById('fullScreenToggle');
        if (fullscreenBtn) {
            fullscreenBtn.addEventListener('click', () => this.toggleFullScreen());
        }
        
        // Device selection
        const cameraSelect = document.getElementById('cameraSelect');
        if (cameraSelect) {
            cameraSelect.addEventListener('change', (e) => this.changeCamera(e.target.value));
        }
        
        const micSelect = document.getElementById('microphoneSelect');
        if (micSelect) {
            micSelect.addEventListener('change', (e) => this.changeMicrophone(e.target.value));
        }
        
        // Tab switching
        const tabButtons = document.querySelectorAll('.tab-button');
        tabButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                // Use currentTarget to get the button element itself, not the clicked child
                const tabName = e.currentTarget.dataset.tab || e.currentTarget.getAttribute('data-tab');
                console.log('Tab button clicked, switching to:', tabName);
                if (tabName) {
                    this.switchTab(tabName);
                } else {
                    console.warn('No tab name found for button:', e.currentTarget);
                }
            });
        });
        
        // Modal controls
        const confirmEndBtn = document.getElementById('confirmEndSession');
        if (confirmEndBtn) {
            confirmEndBtn.addEventListener('click', () => this.endSession());
        }
        
        const cancelEndBtn = document.getElementById('cancelEndSession');
        if (cancelEndBtn) {
            cancelEndBtn.addEventListener('click', () => this.hideEndSessionModal());
        }
        
        // Close modal on outside click
        const modal = document.getElementById('endSessionModal');
        if (modal) {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    this.hideEndSessionModal();
                }
            });
        }
        
        // Fullscreen event listeners
        document.addEventListener('fullscreenchange', () => {
            if (!document.fullscreenElement) {
                // Exited fullscreen
                this.exitFullscreenMode();
            }
        });
        
        // ESC key to exit fullscreen
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && document.fullscreenElement) {
                document.exitFullscreen();
            }
        });
        
        // F11 key for fullscreen toggle
        document.addEventListener('keydown', (e) => {
            if (e.key === 'F11') {
                e.preventDefault();
                this.toggleFullScreen();
            }
        });
    }
    
    joinSession() {
        console.log('Joining session:', this.sessionId);
        this.socket.emit('join_session', {
            session_id: this.sessionId,
            device_info: navigator.userAgent,
            ip_address: 'client_side' // Will be detected server-side
        });
    }
    
    async startCall() {
        console.log('Starting video call...');
        
        try {
            await this.createPeerConnection();
            // Don't show call UI immediately - wait for connection to establish
            this.startSessionTimer();
            this.isInCall = true;
            
            // Create and send offer
            const offer = await this.peerConnection.createOffer();
            await this.peerConnection.setLocalDescription(offer);
            
            this.socket.emit('offer', {
                session_id: this.sessionId,
                offer: offer,
                target_user_id: null // Broadcast to room
            });
            
            this.updateConnectionStatus('Call started - waiting for counselor response', 'info');
            
        } catch (error) {
            console.error('Error starting call:', error);
            this.showError('Failed to start video call');
        }
    }
    
    async createPeerConnection() {
        console.log('Creating peer connection...');
        
        this.peerConnection = new RTCPeerConnection({
            iceServers: this.iceServers
        });
        
        // Add local stream
        if (this.localStream) {
            this.localStream.getTracks().forEach(track => {
                this.peerConnection.addTrack(track, this.localStream);
            });
        }
        
        // Handle remote stream
        this.peerConnection.ontrack = (event) => {
            console.log('Student received remote stream from counselor');
            this.remoteStream = event.streams[0];
            const remoteVideo = document.getElementById('remoteVideo');
            if (remoteVideo) {
                remoteVideo.srcObject = this.remoteStream;
                console.log('Remote video stream attached to video element');
            }
            
            // Show call UI when we receive remote stream - this is a reliable indicator
            if (this.isInCall) {
                console.log('Remote stream received - showing call UI');
                this.showCallUI();
            }
        };
        
        // Handle ICE candidates
        this.peerConnection.onicecandidate = (event) => {
            if (event.candidate) {
                this.socket.emit('ice_candidate', {
                    session_id: this.sessionId,
                    candidate: event.candidate
                });
            }
        };
        
        // Monitor connection state
        this.peerConnection.onconnectionstatechange = () => {
            const state = this.peerConnection.connectionState;
            console.log('Connection state changed:', state);
            
            switch (state) {
                case 'connecting':
                    this.updateConnectionStatus('Connecting to video call...', 'info');
                    break;
                case 'connected':
                    this.updateConnectionStatus('Video call connected', 'success');
                    // Ensure call UI is shown when connected
                    if (this.isInCall) {
                        this.showCallUI();
                    }
                    break;
                case 'disconnected':
                    this.updateConnectionStatus('Connection lost', 'warning');
                    break;
                case 'failed':
                    this.updateConnectionStatus('Connection failed', 'error');
                    this.handleConnectionIssue();
                    break;
                case 'closed':
                    this.updateConnectionStatus('Call ended', 'info');
                    break;
            }
        };
        
        // Monitor ICE connection state
        this.peerConnection.oniceconnectionstatechange = () => {
            const state = this.peerConnection.iceConnectionState;
            console.log('ICE connection state:', state);
            
            if (state === 'connected' || state === 'completed') {
                console.log('ICE connection established - ensuring call UI is visible');
                if (this.isInCall) {
                    this.showCallUI();
                }
            } else if (state === 'failed' || state === 'disconnected') {
                this.handleConnectionIssue();
            }
        };
        
        // Monitor data channel for connection quality
        this.monitorConnectionQuality();
    }
    
    async handleOffer(offer) {
        console.log('Handling WebRTC offer');
        
        if (!this.peerConnection) {
            await this.createPeerConnection();
        }
        
        await this.peerConnection.setRemoteDescription(offer);
        const answer = await this.peerConnection.createAnswer();
        await this.peerConnection.setLocalDescription(answer);
        
        this.socket.emit('answer', {
            session_id: this.sessionId,
            answer: answer
        });
        
        if (!this.isInCall) {
            this.startSessionTimer();
            this.isInCall = true;
        }
        
        // Don't show call UI immediately - wait for connection to establish
        this.updateConnectionStatus('Processing call connection...', 'info');
    }
    
    async handleAnswer(answer) {
        console.log('Handling WebRTC answer');
        
        if (this.peerConnection) {
            await this.peerConnection.setRemoteDescription(answer);
            this.updateConnectionStatus('Call connection established', 'success');
            
            // Show call UI immediately after setting remote description
            console.log('Connection state:', this.peerConnection.connectionState);
            console.log('ICE connection state:', this.peerConnection.iceConnectionState);
            
            // Show call UI after a short delay to ensure DOM is ready
            setTimeout(() => {
                console.log('Checking if we should show call UI...');
                console.log('isInCall:', this.isInCall);
                console.log('Connection state:', this.peerConnection?.connectionState);
                console.log('ICE state:', this.peerConnection?.iceConnectionState);
                
                if (this.isInCall) {
                    this.showCallUI();
                }
            }, 500);
        }
    }
    
    async handleIceCandidate(candidate) {
        if (this.peerConnection && this.peerConnection.remoteDescription) {
            await this.peerConnection.addIceCandidate(candidate);
        }
    }
    
    toggleAudio(isWaitingRoom = false) {
        console.log('Toggling audio, current state:', this.isAudioEnabled, 'waiting room:', isWaitingRoom);
        
        if (this.localStream) {
            const audioTrack = this.localStream.getAudioTracks()[0];
            if (audioTrack) {
                this.isAudioEnabled = !this.isAudioEnabled;
                audioTrack.enabled = this.isAudioEnabled;
                
                console.log('Audio track enabled set to:', audioTrack.enabled);
                
                // Notify other participants (only if not in waiting room)
                if (!isWaitingRoom && this.socket) {
                    this.socket.emit('toggle_audio', {
                        session_id: this.sessionId,
                        audio_enabled: this.isAudioEnabled
                    });
                } else if (isWaitingRoom && this.socket) {
                    this.socket.emit('waiting_room_media_toggle', {
                        session_id: this.sessionId,
                        media_type: 'audio',
                        enabled: this.isAudioEnabled
                    });
                }
                
                // Update all media buttons (both waiting room and call interface)
                this.updateAllMediaButtons();
                
                const status = this.isAudioEnabled ? 'Microphone on' : 'Microphone off';
                this.showNotification(status, this.isAudioEnabled ? 'success' : 'warning');
            } else {
                console.warn('No audio track available for toggle');
                this.showError('No audio track available');
            }
        } else {
            console.warn('No local stream available for audio toggle');
            this.showError('Microphone not initialized. Please refresh the page.');
        }
    }
    
    toggleVideo(isWaitingRoom = false) {
        console.log('Toggling video, current state:', this.isVideoEnabled, 'waiting room:', isWaitingRoom);
        
        if (this.localStream) {
            const videoTrack = this.localStream.getVideoTracks()[0];
            if (videoTrack) {
                this.isVideoEnabled = !this.isVideoEnabled;
                videoTrack.enabled = this.isVideoEnabled;
                
                console.log('Video track enabled set to:', videoTrack.enabled);
                
                // Handle video placeholder visibility
                this.updateVideoPlaceholder();
                
                // Notify other participants (only if not in waiting room)
                if (!isWaitingRoom && this.socket) {
                    this.socket.emit('toggle_video', {
                        session_id: this.sessionId,
                        video_enabled: this.isVideoEnabled
                    });
                } else if (isWaitingRoom && this.socket) {
                    this.socket.emit('waiting_room_media_toggle', {
                        session_id: this.sessionId,
                        media_type: 'video',
                        enabled: this.isVideoEnabled
                    });
                }
                
                // Update all media buttons (both waiting room and call interface)
                this.updateAllMediaButtons();
                
                const status = this.isVideoEnabled ? 'Camera on' : 'Camera off';
                this.showNotification(status, this.isVideoEnabled ? 'success' : 'warning');
            } else {
                console.warn('No video track available for toggle');
                this.showError('No video track available');
            }
        } else {
            console.warn('No local stream available for video toggle');
            this.showError('Camera not initialized. Please refresh the page.');
        }
    }
    
    updateMediaButtons() {
        // Update main call interface buttons
        const audioBtn = document.getElementById('micToggle'); // Changed from 'toggleAudioBtn'
        const videoBtn = document.getElementById('cameraToggle'); // Changed from 'toggleVideoBtn'
        
        if (audioBtn) {
            const icon = audioBtn.querySelector('i');
            if (icon) {
                icon.className = this.isAudioEnabled ? 'fas fa-microphone' : 'fas fa-microphone-slash';
            }
            audioBtn.className = this.isAudioEnabled ? 
                'w-12 h-12 bg-blue-500 hover:bg-blue-600 rounded-full flex items-center justify-center transition-all duration-300 hover:scale-110' : 
                'w-12 h-12 bg-red-500 hover:bg-red-600 rounded-full flex items-center justify-center transition-all duration-300 hover:scale-110';
            
            audioBtn.title = this.isAudioEnabled ? 'Mute microphone' : 'Unmute microphone';
        }
        
        if (videoBtn) {
            const icon = videoBtn.querySelector('i');
            if (icon) {
                icon.className = this.isVideoEnabled ? 'fas fa-video' : 'fas fa-video-slash';
            }
            videoBtn.className = this.isVideoEnabled ? 
                'w-12 h-12 bg-blue-500 hover:bg-blue-600 rounded-full flex items-center justify-center transition-all duration-300 hover:scale-110' : 
                'w-12 h-12 bg-red-500 hover:bg-red-600 rounded-full flex items-center justify-center transition-all duration-300 hover:scale-110';
            
            videoBtn.title = this.isVideoEnabled ? 'Turn off camera' : 'Turn on camera';
        }
    }

    updateWaitingRoomButtons() {
        // Update waiting room buttons
        const waitingRoomMicToggle = document.getElementById('waitingRoomMicToggle');
        const waitingRoomCameraToggle = document.getElementById('waitingRoomCameraToggle');
        
        if (waitingRoomMicToggle) {
            const icon = waitingRoomMicToggle.querySelector('i');
            if (icon) {
                icon.className = this.isAudioEnabled ? 
                    'fas fa-microphone text-blue-600 group-hover:scale-110 transition-transform duration-300' : 
                    'fas fa-microphone-slash text-red-600 group-hover:scale-110 transition-transform duration-300';
            }
            
            const baseClasses = 'w-12 h-12 rounded-full shadow-lg hover:shadow-xl flex items-center justify-center border border-slate-200 transition-all duration-300 hover:scale-110 group';
            waitingRoomMicToggle.className = baseClasses + (this.isAudioEnabled ? ' bg-white' : ' bg-red-50');
            
            waitingRoomMicToggle.title = this.isAudioEnabled ? 'Mute microphone' : 'Unmute microphone';
        }
        
        if (waitingRoomCameraToggle) {
            const icon = waitingRoomCameraToggle.querySelector('i');
            if (icon) {
                icon.className = this.isVideoEnabled ? 
                    'fas fa-video text-blue-600 group-hover:scale-110 transition-transform duration-300' : 
                    'fas fa-video-slash text-red-600 group-hover:scale-110 transition-transform duration-300';
            }
            
            const baseClasses = 'w-12 h-12 rounded-full shadow-lg hover:shadow-xl flex items-center justify-center border border-slate-200 transition-all duration-300 hover:scale-110 group';
            waitingRoomCameraToggle.className = baseClasses + (this.isVideoEnabled ? ' bg-white' : ' bg-red-50');
            
            waitingRoomCameraToggle.title = this.isVideoEnabled ? 'Turn off camera' : 'Turn on camera';
        }
    }

    updateAllMediaButtons() {
        // Update both waiting room and call interface buttons
        this.updateMediaButtons();
        this.updateWaitingRoomButtons();
    }

    updateVideoPlaceholder() {
        // Update video placeholder visibility in waiting room
        const waitingRoomVideo = document.getElementById('waitingRoomVideo');
        const waitingRoomVideoPlaceholder = document.getElementById('waitingRoomVideoPlaceholder');
        
        if (waitingRoomVideo && waitingRoomVideoPlaceholder) {
            if (this.isVideoEnabled) {
                waitingRoomVideo.style.display = 'block';
                waitingRoomVideoPlaceholder.style.display = 'none';
            } else {
                waitingRoomVideo.style.display = 'none';
                waitingRoomVideoPlaceholder.style.display = 'flex';
            }
        }
        
        // Also update main video elements if they exist
        const localVideo = document.getElementById('localVideo');
        if (localVideo) {
            if (this.isVideoEnabled) {
                localVideo.style.opacity = '1';
                localVideo.style.filter = 'none';
            } else {
                localVideo.style.opacity = '0.3';
                localVideo.style.filter = 'blur(10px)';
            }
        }
    }
    
    showWaitingRoom() {
        const waitingRoom = document.getElementById('waitingRoomUI'); // Fixed ID
        const callInterface = document.getElementById('callUI'); // Fixed ID
        
        if (waitingRoom) {
            waitingRoom.classList.remove('hidden');
            console.log('Waiting room shown');
        } else {
            console.warn('Waiting room element not found');
        }
        
        if (callInterface) {
            callInterface.classList.add('hidden');
            console.log('Call interface hidden');
        } else {
            console.warn('Call interface element not found');
        }
        
        this.updateWaitingRoomMessage('Connecting to session...');
        
        // Attach stream to waiting room video if available
        if (this.localStream) {
            const waitingRoomVideo = document.getElementById('waitingRoomVideo');
            if (waitingRoomVideo) {
                waitingRoomVideo.srcObject = this.localStream;
                waitingRoomVideo.muted = true;
                waitingRoomVideo.play().catch(e => console.warn('Failed to play waiting room video:', e));
            }
        }
        
        // Update button states
        this.updateAllMediaButtons();
    }
    
    showCallUI() {
        console.log('=== STUDENT SHOWING CALL UI ===');
        const waitingRoom = document.getElementById('waitingRoomUI');
        const callInterface = document.getElementById('callUI');
        
        console.log('Waiting room element:', waitingRoom);
        console.log('Call interface element:', callInterface);
        
        if (waitingRoom) {
            console.log('Waiting room classes before:', waitingRoom.className);
            waitingRoom.classList.add('hidden');
            console.log('Waiting room classes after:', waitingRoom.className);
        } else {
            console.error('Waiting room element (waitingRoomUI) not found!');
        }
        
        if (callInterface) {
            console.log('Call interface classes before:', callInterface.className);
            callInterface.classList.remove('hidden');
            console.log('Call interface classes after:', callInterface.className);
        } else {
            console.error('Call interface element (callUI) not found!');
        }
        
        // Try to find and activate the first available tab
        const firstTab = document.querySelector('.tab-button');
        if (firstTab) {
            const tabName = firstTab.getAttribute('data-tab');
            if (tabName) {
                console.log('Switching to first available tab:', tabName);
                this.switchTab(tabName);
            }
        } else {
            console.warn('No tab buttons found, attempting to initialize tabs...');
            this.initializeTabs();
        }
        
        // Debug: log all available tabs
        const allTabs = document.querySelectorAll('.tab-button');
        const allContents = document.querySelectorAll('.tab-content');
        console.log('Available tab buttons:', allTabs.length);
        console.log('Available tab contents:', allContents.length);
        
        allTabs.forEach((tab, index) => {
            console.log(`Tab button ${index}:`, tab.getAttribute('data-tab'), tab.classList.toString());
        });
        
        allContents.forEach((content, index) => {
            console.log(`Tab content ${index}:`, content.getAttribute('data-tab'), content.classList.toString());
        });
        
        // Update status and start timer when call UI is shown
        this.updateConnectionStatus('In Session', 'success');
        
        // Mark call as active and start timer
        if (!this.isInCall) {
            this.isInCall = true;
            this.startSessionTimer();
            console.log('Call marked as active and timer started');
        }
        
        // Ensure local video stream is attached
        const localVideo = document.getElementById('localVideo');
        if (localVideo && this.localStream) {
            localVideo.srcObject = this.localStream;
            localVideo.muted = true;
            console.log('Local video stream attached');
        }
        
        console.log('=== STUDENT CALL UI SETUP COMPLETE ===');
    }
    
    updateWaitingRoomMessage(message) {
        const messageElement = document.getElementById('waitingRoomMessage');
        if (messageElement) {
            messageElement.textContent = message;
        } else {
            console.warn('Waiting room message element not found');
        }
    }
    
    updateConnectionStatus(status, type = 'info') {
        // Update the main status text
        const statusTextElement = document.getElementById('statusText');
        if (statusTextElement) {
            statusTextElement.textContent = status;
        }
        
        // Update the status indicator container styling
        const statusIndicatorElement = document.getElementById('statusIndicator');
        if (statusIndicatorElement) {
            // Remove existing status classes more carefully
            const classList = statusIndicatorElement.classList;
            const classesToRemove = Array.from(classList).filter(cls => 
                cls.includes('from-') || cls.includes('to-') || cls.includes('border-') || cls.includes('text-')
            );
            classesToRemove.forEach(cls => classList.remove(cls));
            
            // Add base classes if they don't exist
            if (!classList.contains('px-4')) classList.add('px-4');
            if (!classList.contains('py-2')) classList.add('py-2');
            if (!classList.contains('bg-gradient-to-r')) classList.add('bg-gradient-to-r');
            if (!classList.contains('border')) classList.add('border');
            if (!classList.contains('text-sm')) classList.add('text-sm');
            if (!classList.contains('rounded-full')) classList.add('rounded-full');
            if (!classList.contains('flex')) classList.add('flex');
            if (!classList.contains('items-center')) classList.add('items-center');
            if (!classList.contains('space-x-2')) classList.add('space-x-2');
            if (!classList.contains('shadow-sm')) classList.add('shadow-sm');
            
            // Add appropriate status styling
            switch (type) {
                case 'success':
                    classList.add('from-green-500/20', 'to-emerald-500/20', 'border-green-200', 'text-green-700');
                    break;
                case 'warning':
                    classList.add('from-yellow-500/20', 'to-orange-500/20', 'border-yellow-200', 'text-yellow-700');
                    break;
                case 'error':
                    classList.add('from-red-500/20', 'to-pink-500/20', 'border-red-200', 'text-red-700');
                    break;
                default:
                    classList.add('from-blue-500/20', 'to-indigo-500/20', 'border-blue-200', 'text-blue-700');
            }
        }
        
        // Legacy support - also update connectionStatus if it exists
        const connectionStatusElement = document.getElementById('connectionStatus');
        if (connectionStatusElement) {
            connectionStatusElement.textContent = status;
            
            // Update status styling
            connectionStatusElement.className = 'text-sm font-medium';
            switch (type) {
                case 'success':
                    connectionStatusElement.classList.add('text-green-600');
                    break;
                case 'warning':
                    connectionStatusElement.classList.add('text-yellow-600');
                    break;
                case 'error':
                    connectionStatusElement.classList.add('text-red-600');
                    break;
                default:
                    connectionStatusElement.classList.add('text-blue-600');
            }
        }
        
        // Also update any connection indicators
        this.updateConnectionIndicators(type, type === 'success');
    }
    
    startSessionTimer() {
        this.startTime = new Date();
        this.sessionTimer = setInterval(() => {
            const elapsed = new Date() - this.startTime;
            const hours = Math.floor(elapsed / 3600000);
            const minutes = Math.floor((elapsed % 3600000) / 60000);
            const seconds = Math.floor((elapsed % 60000) / 1000);
            
            // Update the main timer element
            const timerElement = document.getElementById('timer');
            if (timerElement) {
                const timeString = hours > 0 
                    ? `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
                    : `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
                timerElement.textContent = timeString;
            }
            
            // Also update sessionTimer if it exists
            const sessionTimerElement = document.getElementById('sessionTimer');
            if (sessionTimerElement) {
                const timeString = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
                sessionTimerElement.textContent = timeString;
            }
        }, 1000);
    }
    
    stopSessionTimer() {
        if (this.sessionTimer) {
            clearInterval(this.sessionTimer);
            this.sessionTimer = null;
        }
    }
    
    startHeartbeat() {
        this.heartbeatInterval = setInterval(() => {
            if (this.socket && this.socket.connected) {
                this.socket.emit('session_heartbeat', {
                    session_id: this.sessionId
                });
            }
        }, 30000); // Send heartbeat every 30 seconds
    }
    
    stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }
    
    showEndSessionModal() {
        const modal = document.getElementById('endSessionModal');
        if (modal) {
            modal.classList.remove('hidden');
        }
    }
    
    hideEndSessionModal() {
        const modal = document.getElementById('endSessionModal');
        if (modal) {
            modal.classList.add('hidden');
        }
    }
    
    endSession() {
        console.log('Ending session...');
        
        this.socket.emit('end_session', {
            session_id: this.sessionId
        });
        
        this.cleanup();
        this.hideEndSessionModal();
        
        // Redirect to session summary or dashboard
        setTimeout(() => {
            window.location.href = '/student/counseling-sessions';
        }, 2000);
    }
    
    handleSessionEnd(data) {
        console.log('Session ended:', data);
        
        this.stopSessionTimer();
        this.showNotification(`Session ended by ${data.ended_by}`, 'info');
        
        // Show session summary
        this.updateConnectionStatus('Session has ended', 'info');
        
        // Cleanup and redirect
        this.cleanup();
        
        setTimeout(() => {
            window.location.href = '/student/counseling-sessions';
        }, 3000);
    }
    
    cleanup() {
        console.log('Cleaning up video counseling session...');
        
        this.stopSessionTimer();
        this.stopHeartbeat();
        
        // Exit fullscreen if active
        if (document.fullscreenElement) {
            document.exitFullscreen();
        }
        
        // Clean up fullscreen-related handlers
        this.stopControlsAutoHide();
        this.hideFullscreenInfo();
        
        // Close peer connection
        if (this.peerConnection) {
            this.peerConnection.close();
            this.peerConnection = null;
        }
        
        // Stop media streams
        if (this.localStream) {
            this.localStream.getTracks().forEach(track => track.stop());
            this.localStream = null;
        }
        
        if (this.remoteStream) {
            this.remoteStream = null;
        }
        
        // Disconnect socket
        if (this.socket) {
            this.socket.disconnect();
            this.socket = null;
        }
        
        this.isInCall = false;
        this.isConnected = false;
    }
    
    showNotification(message, type = 'info') {
        console.log('Notification:', message);
        
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `fixed top-4 right-4 z-50 p-4 rounded-lg text-white shadow-lg notification`;
        
        switch (type) {
            case 'success':
                notification.classList.add('bg-green-500');
                break;
            case 'warning':
                notification.classList.add('bg-yellow-500');
                break;
            case 'error':
                notification.classList.add('bg-red-500');
                break;
            default:
                notification.classList.add('bg-blue-500');
        }
        
        notification.textContent = message;
        document.body.appendChild(notification);
        
        // Animate in
        setTimeout(() => notification.classList.add('opacity-100'), 100);
        
        // Remove after 5 seconds
        setTimeout(() => {
            notification.classList.add('opacity-0');
            setTimeout(() => notification.remove(), 300);
        }, 5000);
    }
    
    showError(message) {
        console.error('Error:', message);
        this.showNotification(message, 'error');
        this.updateConnectionStatus(message, 'error');
    }
    
    handleMediaError(error) {
        let message = 'Failed to access camera or microphone';
        
        if (error.name === 'NotAllowedError') {
            message = 'Camera and microphone access denied. Please allow permissions and refresh.';
        } else if (error.name === 'NotFoundError') {
            message = 'No camera or microphone found. Please connect a device.';
        } else if (error.name === 'NotReadableError') {
            message = 'Camera or microphone is already in use by another application.';
        }
        
        this.showError(message);
    }
    
    handleDisconnection() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            this.updateConnectionStatus(`Reconnecting... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`, 'warning');
            
            setTimeout(() => {
                if (this.socket) {
                    this.socket.connect();
                }
            }, 2000 * this.reconnectAttempts);
        } else {
            this.showError('Failed to reconnect. Please refresh the page.');
        }
    }
    
    handleConnectionError() {
        this.updateConnectionStatus('Connection error - retrying...', 'error');
    }
    
    switchTab(tabName) {
        console.log('Switching to tab:', tabName);
        
        // Hide all tab contents
        const tabContents = document.querySelectorAll('.tab-content');
        tabContents.forEach(content => {
            content.classList.add('hidden');
            content.classList.remove('active');
        });
        
        // Remove active class from all buttons
        const tabButtons = document.querySelectorAll('.tab-button');
        tabButtons.forEach(button => button.classList.remove('active'));
        
        // Show selected tab content using data-tab attribute
        const selectedContent = document.querySelector(`[data-tab="${tabName}"].tab-content`);
        if (selectedContent) {
            selectedContent.classList.remove('hidden');
            selectedContent.classList.add('active');
            console.log('Activated tab content for:', tabName);
        } else {
            console.warn('Tab content not found for:', tabName);
            console.log('Available tab contents:', document.querySelectorAll('.tab-content'));
        }
        
        // Add active class to selected button
        const selectedButton = document.querySelector(`[data-tab="${tabName}"].tab-button`);
        if (selectedButton) {
            selectedButton.classList.add('active');
            console.log('Activated tab button for:', tabName);
        } else {
            console.warn('Tab button not found for:', tabName);
        }
    }
    
    toggleFullScreen() {
        const videoContainer = document.querySelector('.flex-grow.flex.relative.bg-gradient-to-br');
        const fullscreenBtn = document.getElementById('fullScreenToggle');
        
        if (!videoContainer) {
            console.error('Video container not found');
            return;
        }
        
        if (document.fullscreenElement) {
            // Exit fullscreen
            document.exitFullscreen().then(() => {
                this.exitFullscreenMode();
            }).catch(err => {
                console.error('Error exiting fullscreen:', err);
            });
        } else {
            // Enter fullscreen
            videoContainer.requestFullscreen().then(() => {
                this.enterFullscreenMode();
            }).catch(err => {
                console.error('Error entering fullscreen:', err);
                // Fallback to video element fullscreen if container fails
                const remoteVideo = document.getElementById('remoteVideo');
                if (remoteVideo) {
                    remoteVideo.requestFullscreen().catch(fallbackErr => {
                        console.error('Fallback fullscreen also failed:', fallbackErr);
                    });
                }
            });
        }
        
        // Update button icon
        if (fullscreenBtn) {
            const icon = fullscreenBtn.querySelector('i');
            if (icon) {
                if (document.fullscreenElement) {
                    icon.className = 'fas fa-compress text-white';
                    fullscreenBtn.title = 'Exit Fullscreen';
                } else {
                    icon.className = 'fas fa-expand text-white';
                    fullscreenBtn.title = 'Fullscreen';
                }
            }
        }
    }
    
    enterFullscreenMode() {
        console.log('Entering enhanced fullscreen mode');
        
        // Add fullscreen-specific styles
        const videoContainer = document.querySelector('.flex-grow.flex.relative.bg-gradient-to-br');
        if (videoContainer) {
            videoContainer.classList.add('fullscreen-active');
        }
        
        // Enhance video controls visibility in fullscreen
        const controlBar = document.querySelector('.absolute.bottom-6');
        if (controlBar) {
            controlBar.classList.add('fullscreen-controls');
        }
        
        // Enhance local video positioning in fullscreen
        const localVideoContainer = document.getElementById('selfVideoContainer');
        if (localVideoContainer) {
            localVideoContainer.classList.add('fullscreen-local-video');
        }
        
        // Show fullscreen info overlay
        this.showFullscreenInfo();
        
        // Ensure controls are visible initially, then auto-hide
        this.startControlsAutoHide();
    }
    
    exitFullscreenMode() {
        console.log('Exiting enhanced fullscreen mode');
        
        // Remove fullscreen-specific styles
        const videoContainer = document.querySelector('.flex-grow.flex.relative.bg-gradient-to-br');
        if (videoContainer) {
            videoContainer.classList.remove('fullscreen-active');
        }
        
        const controlBar = document.querySelector('.absolute.bottom-6');
        if (controlBar) {
            controlBar.classList.remove('fullscreen-controls', 'controls-hidden');
        }
        
        const localVideoContainer = document.getElementById('selfVideoContainer');
        if (localVideoContainer) {
            localVideoContainer.classList.remove('fullscreen-local-video');
        }
        
        // Clear auto-hide timer
        this.stopControlsAutoHide();
        
        // Remove fullscreen info overlay
        this.hideFullscreenInfo();
        
        // Update button icon
        const fullscreenBtn = document.getElementById('fullScreenToggle');
        if (fullscreenBtn) {
            const icon = fullscreenBtn.querySelector('i');
            if (icon) {
                icon.className = 'fas fa-expand text-white';
                fullscreenBtn.title = 'Fullscreen';
            }
        }
    }
    
    startControlsAutoHide() {
        const videoContainer = document.querySelector('.flex-grow.flex.relative.bg-gradient-to-br');
        const controlBar = document.querySelector('.absolute.bottom-6');
        
        if (!videoContainer || !controlBar) return;
        
        let hideTimer;
        let isMouseOverControls = false;
        
        const showControls = () => {
            controlBar.classList.remove('controls-hidden');
            clearTimeout(hideTimer);
            
            if (!isMouseOverControls) {
                hideTimer = setTimeout(() => {
                    if (!isMouseOverControls) {
                        controlBar.classList.add('controls-hidden');
                    }
                }, 3000);
            }
        };
        
        const hideControls = () => {
            if (!isMouseOverControls) {
                controlBar.classList.add('controls-hidden');
            }
        };
        
        // Show controls on mouse movement
        videoContainer.addEventListener('mousemove', showControls);
        videoContainer.addEventListener('click', showControls);
        
        // Prevent hiding when hovering over controls
        controlBar.addEventListener('mouseenter', () => {
            isMouseOverControls = true;
            clearTimeout(hideTimer);
        });
        
        controlBar.addEventListener('mouseleave', () => {
            isMouseOverControls = false;
            hideTimer = setTimeout(() => {
                controlBar.classList.add('controls-hidden');
            }, 1000);
        });
        
        // Store references for cleanup
        this.fullscreenMouseHandler = showControls;
        this.fullscreenClickHandler = showControls;
        this.controlsMouseEnter = () => {
            isMouseOverControls = true;
            clearTimeout(hideTimer);
        };
        this.controlsMouseLeave = () => {
            isMouseOverControls = false;
            hideTimer = setTimeout(() => {
                controlBar.classList.add('controls-hidden');
            }, 1000);
        };
        
        // Initial hide timer
        hideTimer = setTimeout(hideControls, 3000);
    }
    
    stopControlsAutoHide() {
        const videoContainer = document.querySelector('.flex-grow.flex.relative.bg-gradient-to-br');
        const controlBar = document.querySelector('.absolute.bottom-6');
        
        if (videoContainer && this.fullscreenMouseHandler) {
            videoContainer.removeEventListener('mousemove', this.fullscreenMouseHandler);
            videoContainer.removeEventListener('click', this.fullscreenClickHandler);
        }
        
        if (controlBar) {
            if (this.controlsMouseEnter) {
                controlBar.removeEventListener('mouseenter', this.controlsMouseEnter);
            }
            if (this.controlsMouseLeave) {
                controlBar.removeEventListener('mouseleave', this.controlsMouseLeave);
            }
        }
    }
    
    showFullscreenInfo() {
        // Remove existing info if any
        this.hideFullscreenInfo();
        
        const videoContainer = document.querySelector('.flex-grow.flex.relative.bg-gradient-to-br');
        if (!videoContainer) return;
        
        const infoOverlay = document.createElement('div');
        infoOverlay.id = 'fullscreenInfo';
        infoOverlay.className = 'absolute top-6 right-6 bg-black/60 backdrop-blur-sm px-4 py-2 rounded-xl text-sm text-white z-10 opacity-0 transition-opacity duration-300';
        infoOverlay.innerHTML = `
            <div class="flex items-center space-x-2">
                <i class="fas fa-expand text-blue-400"></i>
                <span>Fullscreen Mode</span>
            </div>
            <div class="text-xs text-gray-300 mt-1">Press ESC to exit</div>
        `;
        
        videoContainer.appendChild(infoOverlay);
        
        // Animate in
        setTimeout(() => {
            infoOverlay.classList.remove('opacity-0');
            infoOverlay.classList.add('opacity-100');
        }, 100);
        
        // Auto-hide after 4 seconds
        setTimeout(() => {
            infoOverlay.classList.remove('opacity-100');
            infoOverlay.classList.add('opacity-0');
        }, 4000);
    }
    
    hideFullscreenInfo() {
        const existingInfo = document.getElementById('fullscreenInfo');
        if (existingInfo) {
            existingInfo.remove();
        }
    }
    
    async changeCamera(deviceId) {
        if (!deviceId || !this.localStream) return;
        
        try {
            // Stop current video track
            const videoTrack = this.localStream.getVideoTracks()[0];
            if (videoTrack) {
                videoTrack.stop();
            }
            
            // Get new video stream
            const newStream = await navigator.mediaDevices.getUserMedia({
                video: { deviceId: { exact: deviceId } },
                audio: false
            });
            
            // Replace video track
            const newVideoTrack = newStream.getVideoTracks()[0];
            this.localStream.removeTrack(videoTrack);
            this.localStream.addTrack(newVideoTrack);
            
            // Update peer connection
            if (this.peerConnection) {
                const sender = this.peerConnection.getSenders().find(s => 
                    s.track && s.track.kind === 'video'
                );
                if (sender) {
                    await sender.replaceTrack(newVideoTrack);
                }
            }
            
            // Update local video element
            const localVideo = document.getElementById('localVideo');
            if (localVideo) {
                localVideo.srcObject = this.localStream;
            }
            
            this.showNotification('Camera changed successfully', 'success');
            
        } catch (error) {
            console.error('Error changing camera:', error);
            this.showError('Failed to change camera');
        }
    }
    
    async changeMicrophone(deviceId) {
        if (!deviceId || !this.localStream) return;
        
        try {
            // Stop current audio track
            const audioTrack = this.localStream.getAudioTracks()[0];
            if (audioTrack) {
                audioTrack.stop();
            }
            
            // Get new audio stream
            const newStream = await navigator.mediaDevices.getUserMedia({
                audio: { deviceId: { exact: deviceId } },
                video: false
            });
            
            // Replace audio track
            const newAudioTrack = newStream.getAudioTracks()[0];
            this.localStream.removeTrack(audioTrack);
            this.localStream.addTrack(newAudioTrack);
            
            // Update peer connection
            if (this.peerConnection) {
                const sender = this.peerConnection.getSenders().find(s => 
                    s.track && s.track.kind === 'audio'
                );
                if (sender) {
                    await sender.replaceTrack(newAudioTrack);
                }
            }
            
            this.showNotification('Microphone changed successfully', 'success');
            
        } catch (error) {
            console.error('Error changing microphone:', error);
            this.showError('Failed to change microphone');
        }
    }
    
    updateConnectionIndicators(type, isConnected) {
        // Update class-based indicators
        const indicators = document.querySelectorAll('.connection-indicator');
        indicators.forEach(indicator => {
            indicator.className = 'connection-indicator';
            if (isConnected) {
                indicator.classList.add('connection-excellent');
            } else {
                indicator.classList.add('connection-poor');
            }
        });
        
        // Update the main connection indicator by ID
        const connectionIndicator = document.getElementById('connectionIndicator');
        if (connectionIndicator) {
            // Remove all status classes
            connectionIndicator.classList.remove('bg-emerald-500', 'bg-yellow-500', 'bg-red-500', 'bg-blue-500');
            
            // Add appropriate status class based on type
            switch (type) {
                case 'success':
                    connectionIndicator.classList.add('bg-emerald-500');
                    break;
                case 'warning':
                    connectionIndicator.classList.add('bg-yellow-500');
                    break;
                case 'error':
                    connectionIndicator.classList.add('bg-red-500');
                    break;
                default:
                    connectionIndicator.classList.add('bg-blue-500');
            }
        }
        
        // Update connection quality text
        const connectionQuality = document.getElementById('connectionQuality');
        if (connectionQuality) {
            switch (type) {
                case 'success':
                    connectionQuality.textContent = 'Excellent';
                    connectionQuality.className = 'text-xs font-medium text-emerald-800';
                    break;
                case 'warning':
                    connectionQuality.textContent = 'Fair';
                    connectionQuality.className = 'text-xs font-medium text-yellow-800';
                    break;
                case 'error':
                    connectionQuality.textContent = 'Poor';
                    connectionQuality.className = 'text-xs font-medium text-red-800';
                    break;
                default:
                    connectionQuality.textContent = 'Connecting';
                    connectionQuality.className = 'text-xs font-medium text-blue-800';
            }
        }
    }
    
    updateParticipantIndicators(counselorPresent = false, studentPresent = true) {
        // Update counselor indicator
        const counselorIndicator = document.getElementById('counselorIndicator');
        const counselorStatus = counselorIndicator?.parentElement?.nextElementSibling;
        
        if (counselorIndicator) {
            counselorIndicator.className = counselorPresent ? 
                'w-4 h-4 rounded-full bg-emerald-500' : 
                'w-4 h-4 rounded-full bg-slate-300';
                
            // Update the ping animation div
            const pingDiv = counselorIndicator.nextElementSibling;
            if (pingDiv) {
                pingDiv.className = counselorPresent ?
                    'absolute inset-0 rounded-full bg-emerald-500 animate-ping opacity-75' :
                    'absolute inset-0 rounded-full bg-slate-300 animate-ping opacity-75';
            }
        }
        
        if (counselorStatus) {
            counselorStatus.textContent = counselorPresent ? 'Counselor (Ready)' : 'Counselor';
            counselorStatus.className = counselorPresent ? 
                'text-sm font-medium text-emerald-600' : 
                'text-sm font-medium text-slate-600';
        }
        
        // Update student indicator (should always be green for current user)
        const studentIndicator = document.getElementById('studentIndicator');
        const studentStatus = studentIndicator?.parentElement?.nextElementSibling;
        
        if (studentIndicator) {
            studentIndicator.className = 'w-4 h-4 rounded-full bg-emerald-500';
            
            // Update the ping animation div
            const pingDiv = studentIndicator.nextElementSibling;
            if (pingDiv) {
                pingDiv.className = 'absolute inset-0 rounded-full bg-emerald-500 animate-ping opacity-75';
            }
        }
        
        if (studentStatus) {
            studentStatus.textContent = 'You (Connected)';
            studentStatus.className = 'text-sm font-medium text-emerald-600';
        }
    }
    
    showJoinCallButton() {
        const joinCallBtn = document.getElementById('joinCallBtn');
        if (joinCallBtn) {
            joinCallBtn.classList.remove('hidden');
            joinCallBtn.disabled = false;
        }
        
        this.updateWaitingRoomMessage('Ready to start! Click "Join Call" to begin.');
    }
    
    showRecordingIndicator(isRecording) {
        const recordingIndicator = document.getElementById('recordingIndicator');
        if (recordingIndicator) {
            if (isRecording) {
                recordingIndicator.classList.remove('hidden');
            } else {
                recordingIndicator.classList.add('hidden');
            }
        }
    }
    
    handleRemoteAudioToggle(data) {
        console.log(`${data.name} ${data.audio_enabled ? 'enabled' : 'disabled'} their microphone`);
        // Could update UI to show remote user's audio state
    }
    
    handleRemoteVideoToggle(data) {
        console.log(`${data.name} ${data.video_enabled ? 'enabled' : 'disabled'} their camera`);
        // Could update UI to show remote user's video state
    }
    
    handleCounselorDisconnect() {
        this.showNotification('Counselor has left the session', 'warning');
        this.updateConnectionStatus('Waiting for counselor to return...', 'warning');
    }
    
    handleConnectionIssue() {
        this.showNotification('Connection issues detected. Trying to reconnect...', 'warning');
        this.updateConnectionStatus('Connection unstable - attempting to reconnect', 'warning');
    }
    
    monitorConnectionQuality() {
        if (!this.peerConnection) return;
        
        setInterval(async () => {
            try {
                const stats = await this.peerConnection.getStats();
                let inboundRtp = null;
                
                stats.forEach(report => {
                    if (report.type === 'inbound-rtp' && report.kind === 'video') {
                        inboundRtp = report;
                    }
                });
                
                if (inboundRtp) {
                    const quality = this.calculateConnectionQuality(inboundRtp);
                    this.updateConnectionQuality(quality);
                }
                
            } catch (error) {
                console.error('Error monitoring connection quality:', error);
            }
        }, 5000);
    }
    
    calculateConnectionQuality(stats) {
        // Simple quality calculation based on packet loss and jitter
        const packetLossRate = stats.packetsLost / (stats.packetsReceived + stats.packetsLost);
        const jitter = stats.jitter || 0;
        
        if (packetLossRate < 0.02 && jitter < 0.03) {
            return 'excellent';
        } else if (packetLossRate < 0.05 && jitter < 0.08) {
            return 'good';
        } else {
            return 'poor';
        }
    }
    
    updateConnectionQuality(quality) {
        this.connectionQuality = quality;
        
        // Emit quality data to other participants
        if (this.socket && this.socket.connected) {
            this.socket.emit('connection_quality', {
                session_id: this.sessionId,
                quality: {
                    level: quality,
                    timestamp: Date.now()
                }
            });
        }
        
        // Update UI indicators
        const qualityElement = document.getElementById('connectionQuality');
        if (qualityElement) {
            qualityElement.textContent = quality.charAt(0).toUpperCase() + quality.slice(1);
            qualityElement.className = `connection-${quality}`;
        }
    }
    
    // Method to manually initialize tabs if needed
    initializeTabs() {
        console.log('Manually initializing tabs...');
        
        // Find all tab buttons and contents
        const tabButtons = document.querySelectorAll('.tab-button');
        const tabContents = document.querySelectorAll('.tab-content');
        
        console.log('Found tab buttons:', tabButtons.length);
        console.log('Found tab contents:', tabContents.length);
        
        if (tabButtons.length === 0 || tabContents.length === 0) {
            console.error('No tabs found to initialize');
            return;
        }
        
        // Hide all contents first
        tabContents.forEach(content => {
            content.classList.add('hidden');
            content.classList.remove('active');
        });
        
        // Remove active from all buttons
        tabButtons.forEach(button => {
            button.classList.remove('active');
        });
        
        // Activate first tab
        const firstButton = tabButtons[0];
        const firstTabName = firstButton.getAttribute('data-tab');
        
        if (firstTabName) {
            console.log('Activating first tab:', firstTabName);
            this.switchTab(firstTabName);
        } else {
            console.error('First tab button has no data-tab attribute');
        }
    }
    
    // Method to force show tabs (for debugging)
    forceShowTabs() {
        console.log('Force showing all tabs for debugging...');
        const tabContents = document.querySelectorAll('.tab-content');
        tabContents.forEach((content, index) => {
            console.log(`Tab content ${index}:`, content.getAttribute('data-tab'), 'hidden?', content.classList.contains('hidden'));
            if (index === 0) {
                content.classList.remove('hidden');
                content.classList.add('active');
            }
        });
   }
    
    // Debug method for testing tabs from console
    debugTabs() {
        console.log('=== TAB DEBUGGING ===');
        const tabButtons = document.querySelectorAll('.tab-button');
        const tabContents = document.querySelectorAll('.tab-content');
        
        console.log('Tab buttons found:', tabButtons.length);
        tabButtons.forEach((btn, i) => {
            console.log(`Button ${i}:`, btn.getAttribute('data-tab'), 'classes:', btn.className);
        });
        
        console.log('Tab contents found:', tabContents.length);
        tabContents.forEach((content, i) => {
            console.log(`Content ${i}:`, content.getAttribute('data-tab'), 'classes:', content.className);
        });
        
        // Try to switch to info tab
        console.log('Attempting to switch to info tab...');
        this.switchTab('info');
        
        console.log('=== END TAB DEBUGGING ===');
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    // Get session data from page
    const sessionData = window.sessionData || {};
    
    if (sessionData.sessionId && sessionData.userId) {
        console.log('Initializing video counseling for session:', sessionData.sessionId);
        window.videoCounselingClient = new VideoCounselingClient(
            sessionData.sessionId,
            sessionData.userId,
            sessionData.userName
        );
    } else {
        console.error('Missing session data for video counseling');
        alert('Session data missing. Please go back and try again.');
    }
});

// Handle page unload
window.addEventListener('beforeunload', function() {
    if (window.videoCounselingClient) {
        window.videoCounselingClient.cleanup();
    }
});

// Handle tab visibility changes
document.addEventListener('visibilitychange', function() {
    if (window.videoCounselingClient) {
        if (document.hidden) {
            // Page is hidden - could pause video or reduce quality
        } else {
            // Page is visible again - restore normal operation
        }
    }
});