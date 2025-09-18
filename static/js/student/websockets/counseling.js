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
    this.maxReconnectAttempts = 8;
        this.connectionQuality = 'unknown';
    this.pendingIceCandidates = [];
    this.reconnectInProgress = false;
    this.wasInCallBeforeDisconnect = false;
    this.persistKey = `videoCounseling:${this.sessionId}:${this.userId}`;
    this._recoveryTimer = null;
    this._qualityInterval = null;
        
        // ICE servers configuration (prefer server-injected TURN if present)
        const injectedIce = (typeof window !== 'undefined' && Array.isArray(window.PG_ICE_SERVERS)) ? window.PG_ICE_SERVERS : null;
        this.iceServers = injectedIce && injectedIce.length > 0 ? injectedIce : [
            { urls: 'stun:stun.l.google.com:19302' },
            { urls: 'stun:stun1.l.google.com:19302' },
            { urls: 'stun:stun2.l.google.com:19302' }
        ];
        try {
            const flatUrls = (this.iceServers || []).flatMap(s => Array.isArray(s.urls) ? s.urls : [s.urls]);
            const hasTurn = flatUrls.some(u => typeof u === 'string' && u.startsWith('turn'));
            if (!hasTurn) {
                console.warn('[VideoCounseling][Student] No TURN servers configured. Cross-ISP / mobile calls may show black video. Configure TURN_HOST or ICE_SERVERS_JSON.');
            }
        } catch (e) {}
        
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
            this.restoreLocalState();
            this.initializeSocket();
            this.setupEventListeners();
            this.installNavigationGuards();
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
            if (this.wasInCallBeforeDisconnect) {
                // Attempt to restore session/call after reconnect
                this.onSocketReconnected();
            } else {
                this.joinSession();
            }
            this.startHeartbeat();
        });
        
        this.socket.on('disconnect', () => {
            console.log('Disconnected from video counseling server');
            this.isConnected = false;
            this.updateConnectionStatus('Disconnected from server', 'error');
            this.stopHeartbeat();
            this.wasInCallBeforeDisconnect = this.isInCall;
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
            if (data.status === 'ready' && data.all_ready) {
                this.updateConnectionStatus('Ready to start call - waiting for counselor to begin', 'success');
                this.showJoinCallButton();
            } else {
                this.updateConnectionStatus('Waiting for all participants to be ready...', 'info');
            }
        });
        
        this.socket.on('session_waiting', (data) => {
            console.log('Session waiting:', data);
            if (!data.has_counselor) {
                this.updateConnectionStatus('Waiting for counselor to join...', 'info');
            } else if (!data.has_student) {
                this.updateConnectionStatus('Waiting for student to join...', 'info');
            } else {
                this.updateConnectionStatus('Waiting for participants to be ready...', 'info');
            }
        });
        
        this.socket.on('call_starting', (data) => {
            console.log('Call is starting:', data);
            this.updateConnectionStatus('Call is starting! Join when ready.', 'success');
            this.showJoinCallButton();
        });
        
        this.socket.on('call_joined', (data) => {
            console.log('Successfully joined call:', data);
            this.showCallUI();
            this.updateConnectionStatus('Connected to call', 'success');
        });
        
        // Apply initial media state for other participants so placeholders are correct on first render
        this.socket.on('initial_media_state', (payload) => {
            try {
                if (!payload || !Array.isArray(payload.participants)) return;
                payload.participants.forEach(p => {
                    if (p.user_id === this.userId) return;
                    const remoteVideo = document.getElementById('remoteVideo');
                    const remotePlaceholder = document.getElementById('remoteVideoPlaceholder');
                    const videoOn = !!p.video_enabled;
                    if (remoteVideo && remotePlaceholder) {
                        if (videoOn) {
                            remotePlaceholder.classList.add('hidden');
                            remoteVideo.classList.remove('hidden');
                            if (remoteVideo.readyState >= 2) {
                                remoteVideo.play().catch(() => {});
                            }
                        } else {
                            remoteVideo.classList.add('hidden');
                            remotePlaceholder.classList.remove('hidden');
                        }
                    }
                });
            } catch (e) {
                console.warn('Failed to apply initial media state:', e);
            }
        });
        
        this.socket.on('user_joined_call', (data) => {
            console.log('User joined call:', data.name);
            this.showNotification(`${data.name} joined the call`, 'info');
        });
        
        this.socket.on('offer_received', async (data) => {
            console.log('Received WebRTC offer from:', data.from_name);
            try {
                await this.handleOffer(data);
            } catch (error) {
                console.error('Error handling offer:', error);
                this.showError('Failed to process video call offer');
            }
        });
        
        this.socket.on('answer_received', async (data) => {
            console.log('Received WebRTC answer');
            try {
                await this.handleAnswer(data);
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
        
        this.socket.on('screen_share_started', (data) => {
            console.log('🖥️ Screen sharing started by counselor:', data.name);
            this.showNotification(`${data.name} started screen sharing`, 'info');
            this.handleScreenShareStarted(data);
        });
        
        this.socket.on('screen_share_stopped', (data) => {
            console.log('🛑 Screen sharing stopped by counselor:', data.name);
            this.showNotification(`${data.name} stopped screen sharing`, 'info');
            this.handleScreenShareStopped(data);
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
        
        // Peer requests renegotiation after they reconnect
        this.socket.on('reconnect_request', async (data) => {
            console.log('Peer requested reconnection/renegotiation:', data);
            try {
                if (this.peerConnection) {
                    const offer = await this.peerConnection.createOffer({ iceRestart: true });
                    await this.peerConnection.setLocalDescription(offer);
                    this.socket.emit('offer', {
                        session_id: this.sessionId,
                        offer: offer,
                        target_user_id: data.user_id || null
                    });
                }
            } catch (e) {
                console.warn('Failed to renegotiate on reconnect_request:', e);
            }
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
        console.log('🎥 Requesting media access...');
        this.updateConnectionStatus('Requesting camera and microphone access...', 'info');
        
        // Check if getUserMedia is supported
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error('getUserMedia is not supported in this browser');
        }
        
        // First, let's check what devices are available (without permissions)
        try {
            const devices = await navigator.mediaDevices.enumerateDevices();
            const videoInputs = devices.filter(device => device.kind === 'videoinput');
            const audioInputs = devices.filter(device => device.kind === 'audioinput');
            
            console.log('📱 Devices detected before permission:');
            console.log(`  - Video inputs: ${videoInputs.length}`);
            console.log(`  - Audio inputs: ${audioInputs.length}`);
            
            if (videoInputs.length === 0 && audioInputs.length === 0) {
                throw new Error('No media devices detected on this system');
            }
        } catch (enumError) {
            console.warn('⚠️ Could not enumerate devices:', enumError);
        }
        
        // Check current permissions if supported
        if (navigator.permissions) {
            try {
                const cameraPermission = await navigator.permissions.query({ name: 'camera' });
                const microphonePermission = await navigator.permissions.query({ name: 'microphone' });
                
                console.log('🔐 Current permissions:');
                console.log(`  - Camera: ${cameraPermission.state}`);
                console.log(`  - Microphone: ${microphonePermission.state}`);
                
                if (cameraPermission.state === 'denied' && microphonePermission.state === 'denied') {
                    throw new Error('Both camera and microphone permissions are denied');
                }
            } catch (permError) {
                console.warn('⚠️ Could not check permissions:', permError);
            }
        }
        
        try {
            // Start with the most basic constraints possible
            let constraints = {
                video: true,
                audio: true
            };
            
            console.log('🎬 Requesting media with basic constraints first:', constraints);
            
            try {
                // Try basic constraints first
                this.localStream = await navigator.mediaDevices.getUserMedia(constraints);
                console.log('✅ Media access granted with basic constraints');
            } catch (basicError) {
                console.log('⚠️ Basic constraints failed, trying video only...', basicError);
                
                // Try video only
                try {
                    constraints = { video: true, audio: false };
                    this.localStream = await navigator.mediaDevices.getUserMedia(constraints);
                    console.log('✅ Video-only access granted');
                    this.isAudioEnabled = false;
                } catch (videoError) {
                    console.log('⚠️ Video only failed, trying audio only...', videoError);
                    
                    // Try audio only
                    try {
                        constraints = { video: false, audio: true };
                        this.localStream = await navigator.mediaDevices.getUserMedia(constraints);
                        console.log('✅ Audio-only access granted');
                        this.isVideoEnabled = false;
                    } catch (audioError) {
                        console.error('❌ All media access attempts failed');
                        console.error('Final error details:', {
                            basic: basicError.name + ': ' + basicError.message,
                            video: videoError.name + ': ' + videoError.message,
                            audio: audioError.name + ': ' + audioError.message
                        });
                        throw basicError; // Throw the original error
                    }
                }
            }
            
            console.log('🎵 Local stream tracks:', this.localStream.getTracks());
            
            // Verify we have the expected tracks
            const videoTracks = this.localStream.getVideoTracks();
            const audioTracks = this.localStream.getAudioTracks();
            
            console.log('✅ Video tracks:', videoTracks.length);
            console.log('✅ Audio tracks:', audioTracks.length);
            
            // Update enabled states based on what we actually got
            if (videoTracks.length === 0) {
                console.warn('⚠️ No video track available');
                this.isVideoEnabled = false;
            }
            
            if (audioTracks.length === 0) {
                console.warn('⚠️ No audio track available');
                this.isAudioEnabled = false;
            }
            
            // Set track states based on current preferences
            videoTracks.forEach(track => {
                track.enabled = this.isVideoEnabled;
                console.log('Video track enabled:', track.enabled);
            });
            
            audioTracks.forEach(track => {
                track.enabled = this.isAudioEnabled;
                console.log('Audio track enabled:', track.enabled);
            });
            
            // Try to enhance local media quality (1080p@30fps, high bitrate)
            try {
                await this.enhanceLocalMediaQuality('init');
            } catch (e) {
                console.warn('Could not apply high-quality constraints initially:', e?.name || e);
            }

            // Attach to waiting room video element
            const waitingRoomVideo = document.getElementById('waitingRoomVideo');
            if (waitingRoomVideo && videoTracks.length > 0) {
                console.log('✅ Attaching stream to waiting room video');
                waitingRoomVideo.srcObject = this.localStream;
                waitingRoomVideo.muted = true;
                
                waitingRoomVideo.onloadedmetadata = () => {
                    waitingRoomVideo.play().catch(e => {
                        console.warn('Error playing waiting room video:', e);
                    });
                };
                
                // Force play if metadata is already loaded
                if (waitingRoomVideo.readyState >= 2) {
                    waitingRoomVideo.play().catch(e => {
                        console.warn('Error playing waiting room video on ready state:', e);
                    });
                }
            } else {
                console.warn('⚠️ Waiting room video element not found or no video tracks');
            }
            
            // Also attach to main local video element if it exists
            const localVideo = document.getElementById('localVideo');
            if (localVideo && videoTracks.length > 0) {
                console.log('✅ Attaching stream to local video');
                localVideo.srcObject = this.localStream;
                localVideo.muted = true;
                
                localVideo.onloadedmetadata = () => {
                    localVideo.play().catch(e => {
                        console.warn('Error playing local video:', e);
                    });
                };
            }
            
            // Populate device lists
            await this.populateDeviceList();
            
            // Initialize button states
            this.updateAllMediaButtons();
            this.updateVideoPlaceholder();
            
            // Show success message
            let statusMessage = 'Media ready: ';
            if (videoTracks.length > 0 && audioTracks.length > 0) {
                statusMessage += 'Camera and microphone';
            } else if (videoTracks.length > 0) {
                statusMessage += 'Camera only';
            } else if (audioTracks.length > 0) {
                statusMessage += 'Microphone only';
            } else {
                statusMessage += 'No media devices';
            }
            
            this.updateConnectionStatus(statusMessage, 'success');
            console.log('✅ Media initialization completed successfully');
            
        } catch (error) {
            console.error('❌ Failed to access media devices:', error);
            this.handleMediaError(error);
        }
    }
    
    async populateDeviceList() {
        try {
            console.log('Populating device list after media access...');
            
            // Check if media access has been granted
            if (!this.localStream) {
                console.warn('Cannot populate device list - no media access yet');
                return;
            }
            
            const devices = await navigator.mediaDevices.enumerateDevices();
            console.log('Available devices:', devices);
            
            const videoDevices = devices.filter(device => 
                device.kind === 'videoinput' && device.label // Only include devices with labels
            );
            const audioDevices = devices.filter(device => 
                device.kind === 'audioinput' && device.label // Only include devices with labels
            );
            
            console.log('Video devices found:', videoDevices.length);
            console.log('Audio devices found:', audioDevices.length);
            
            // Populate camera select
            const cameraSelect = document.getElementById('cameraSelect');
            if (cameraSelect && videoDevices.length > 0) {
                cameraSelect.innerHTML = '';
                videoDevices.forEach((device, index) => {
                    const option = document.createElement('option');
                    option.value = device.deviceId;
                    option.textContent = device.label || `Camera ${index + 1}`;
                    cameraSelect.appendChild(option);
                });
                console.log('Camera select populated with', videoDevices.length, 'devices');
            } else {
                console.warn('Camera select element not found or no video devices available');
            }
            
            // Populate microphone select
            const micSelect = document.getElementById('microphoneSelect');
            if (micSelect && audioDevices.length > 0) {
                micSelect.innerHTML = '';
                audioDevices.forEach((device, index) => {
                    const option = document.createElement('option');
                    option.value = device.deviceId;
                    option.textContent = device.label || `Microphone ${index + 1}`;
                    micSelect.appendChild(option);
                });
                console.log('Microphone select populated with', audioDevices.length, 'devices');
            } else {
                console.warn('Microphone select element not found or no audio devices available');
            }
            
        } catch (error) {
            console.error('Error populating device list:', error);
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
        // Mobile floating end call button
        const endCallFab = document.getElementById('endCallFab');
        if (endCallFab) {
            endCallFab.addEventListener('click', () => this.showEndSessionModal());
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

        // Mobile side panel open/close
        const mobilePanelButton = document.getElementById('mobilePanelButton');
        const mobilePanelClose = document.getElementById('mobilePanelClose');
        const sidePanel = document.getElementById('sidePanel');
    if (mobilePanelButton && sidePanel) {
            mobilePanelButton.addEventListener('click', () => {
        sidePanel.classList.add('mobile-open');
        try { document.body.style.overflow = 'hidden'; } catch (_) {}
            });
        }
        if (mobilePanelClose && sidePanel) {
            mobilePanelClose.addEventListener('click', () => {
        sidePanel.classList.remove('mobile-open');
        try { document.body.style.overflow = ''; } catch (_) {}
            });
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
        console.log('Joining video call...');
        
        try {
            // Emit join_call event to server
            this.socket.emit('join_call', {
                session_id: this.sessionId
            });
            
            this.updateConnectionStatus('Joining call...', 'info');
            
            // Initialize peer connection for when we receive an offer
            await this.createPeerConnection();
            
        } catch (error) {
            console.error('Error joining call:', error);
            this.showError('Failed to join video call');
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
        // Bump outbound video quality if possible
        try {
            await this.applyHighQualitySenderParams();
        } catch (e) {
            console.warn('Could not set high-quality sender params:', e?.name || e);
        }
        
        // Handle remote stream
        this.peerConnection.ontrack = (event) => {
            console.log('Student received remote stream from counselor');
            this.remoteStream = event.streams[0];
            const remoteVideo = document.getElementById('remoteVideo');
            const remotePlaceholder = document.getElementById('remoteVideoPlaceholder');
            if (remoteVideo) {
                remoteVideo.srcObject = this.remoteStream;
                // Ensure playback starts even with autoplay policies
                const tryPlay = () => {
                    remoteVideo.play().catch(e => {
                        console.warn('Remote video play blocked, will retry on unmute/metadata:', e?.name || e);
                    });
                };
                // Play on metadata load
                remoteVideo.onloadedmetadata = () => {
                    tryPlay();
                };
                // If already have metadata, try immediately
                if (remoteVideo.readyState >= 2) {
                    tryPlay();
                }
                // Also try when the incoming track becomes unmuted
                if (event.track) {
                    event.track.onunmute = () => {
                        tryPlay();
                        if (remotePlaceholder) remotePlaceholder.classList.add('hidden');
                        remoteVideo.classList.remove('hidden');
                    };
                    event.track.onmute = () => {
                        if (remotePlaceholder) remotePlaceholder.classList.remove('hidden');
                        remoteVideo.classList.add('hidden');
                    };
                }
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
            if (this._recoveryTimer) { clearTimeout(this._recoveryTimer); this._recoveryTimer = null; }
                    break;
                case 'disconnected':
                    this.updateConnectionStatus('Connection lost', 'warning');
            this.scheduleConnectionRecovery();
                    break;
                case 'failed':
                    this.updateConnectionStatus('Connection failed', 'error');
                    this.handleConnectionIssue();
            this.scheduleConnectionRecovery(true);
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
                // Attempt ICE restart if in-call
                if (this.isInCall && !this.reconnectInProgress) {
                    this.restartIceSafely();
                }
                this.scheduleConnectionRecovery(state === 'failed');
            }
        };
        
        // Monitor data channel for connection quality
        this.monitorConnectionQuality();
    }

    async applyHighQualitySenderParams() {
        if (!this.peerConnection) return;
        const sender = this.peerConnection.getSenders().find(s => s.track && s.track.kind === 'video');
        if (!sender) return;
        const params = sender.getParameters() || {};
        params.degradationPreference = 'maintain-framerate';
        // Prefer a single high-quality encoding; browsers may clamp values
        const maxBitrate = 2500_000; // ~2.5 Mbps
        const maxFr = 30;
        params.encodings = [{ maxBitrate, maxFramerate: maxFr, scaleResolutionDownBy: 1 }];
        try {
            await sender.setParameters(params);
        } catch (e) {
            // Some browsers require renegotiation before setParameters
            console.debug('setParameters failed (will ignore if unsupported):', e?.name || e);
        }
    }

    async enhanceLocalMediaQuality(context = 'manual') {
        if (!this.localStream) return;
        const vt = this.localStream.getVideoTracks()[0];
        if (!vt) return;
        // Apply ideal 1080p@30fps; browser may adapt
        const constraints = {
            width: { ideal: 1920 },
            height: { ideal: 1080 },
            frameRate: { ideal: 30, max: 30 }
        };
        try {
            await vt.applyConstraints(constraints);
        } catch (e) {
            console.debug(`applyConstraints failed during ${context}:`, e?.name || e);
        }
    }

    async restartIceSafely() {
        if (!this.peerConnection) return;
        try {
            this.reconnectInProgress = true;
            this.updateConnectionStatus('Re-establishing media path…', 'warning');
            const offer = await this.peerConnection.createOffer({ iceRestart: true });
            await this.peerConnection.setLocalDescription(offer);
            this.socket.emit('offer', {
                session_id: this.sessionId,
                offer: offer,
                target_user_id: null
            });
        } catch (e) {
            console.warn('ICE restart failed:', e);
        } finally {
            setTimeout(() => { this.reconnectInProgress = false; }, 1500);
        }
    }
    
    async handleOffer(data) {
        console.log('Handling WebRTC offer from:', data.from_name);
        
        if (!this.peerConnection) {
            await this.createPeerConnection();
        }
        
        try {
            await this.peerConnection.setRemoteDescription(data.offer);
            const answer = await this.peerConnection.createAnswer();
            await this.peerConnection.setLocalDescription(answer);
            
            this.socket.emit('answer', {
                session_id: this.sessionId,
                answer: answer,
                offer_id: data.offer_id,
                target_user_id: data.from_user_id
            });
            
            if (!this.isInCall) {
                this.startSessionTimer();
                this.isInCall = true;
            }
            
            this.updateConnectionStatus('Connecting to call...', 'info');
            // Flush any ICE candidates that arrived early
            this.drainPendingIceCandidates();
            
        } catch (error) {
            console.error('Error processing offer:', error);
            this.showError('Failed to process call connection');
        }
    }
    
    async handleAnswer(data) {
        console.log('Handling WebRTC answer');
        
        if (this.peerConnection) {
            try {
                await this.peerConnection.setRemoteDescription(data.answer);
                this.updateConnectionStatus('Call connection established', 'success');
                // Flush any ICE candidates that arrived early
                this.drainPendingIceCandidates();
                
                // Show call UI after connection is established
                setTimeout(() => {
                    console.log('Showing call UI after answer processed');
                    if (this.isInCall) {
                        this.showCallUI();
                    }
                }, 500);
                
            } catch (error) {
                console.error('Error setting remote description:', error);
                this.showError('Failed to establish call connection');
            }
        }
    }
    
    async handleIceCandidate(candidate) {
        try {
            if (!candidate) return; // Skip null end-of-candidates
            // Queue candidates until peer connection is ready with a remote description
            if (!this.peerConnection || !this.peerConnection.remoteDescription) {
                this.pendingIceCandidates.push(candidate);
                return;
            }
            await this.peerConnection.addIceCandidate(candidate);
        } catch (err) {
            console.error('Failed to add ICE candidate:', err);
        }
    }

    drainPendingIceCandidates() {
        if (!this.peerConnection || !this.peerConnection.remoteDescription) return;
        if (this.pendingIceCandidates.length === 0) return;
        console.log(`Adding ${this.pendingIceCandidates.length} queued ICE candidates`);
        const queue = this.pendingIceCandidates;
        this.pendingIceCandidates = [];
        queue.forEach(async (cand) => {
            try {
                await this.peerConnection.addIceCandidate(cand);
            } catch (err) {
                console.warn('Error adding queued ICE candidate:', err);
            }
        });
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
                // Persist preference for reconnection restore
                this.persistLocalState();
                
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
                // Persist preference for reconnection restore
                this.persistLocalState();
                
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
        const localPlaceholder = document.getElementById('localVideoPlaceholder');
        if (localVideo) {
            if (this.isVideoEnabled) {
                localVideo.classList.remove('hidden');
                if (localPlaceholder) localPlaceholder.classList.add('hidden');
            } else {
                localVideo.classList.add('hidden');
                if (localPlaceholder) localPlaceholder.classList.remove('hidden');
            }
        }
    }
    
    showWaitingRoom() {
        const waitingRoom = document.getElementById('waitingRoomUI'); // Fixed ID
        const callInterface = document.getElementById('callUI'); // Fixed ID
    const header = document.getElementById('videoHeader');
        
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
        // Ensure header is visible when not in call
        if (header) {
            header.classList.remove('in-call-hide');
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
    const header = document.getElementById('videoHeader');
        
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
        // On small screens, hide the header to maximize video area
        if (header) {
            header.classList.add('in-call-hide');
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
            this.persistLocalState();
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
        
    // Do not force disconnect socket here to preserve reconnection
        
    this.isInCall = false;
        this.isConnected = false;
    this.pendingIceCandidates = [];
    this.persistLocalState();

        // Ensure mobile overlay is closed and scroll restored
        try {
            const sidePanel = document.getElementById('sidePanel');
            if (sidePanel) sidePanel.classList.remove('mobile-open');
            document.body.style.overflow = '';
        } catch (_) {}
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
        let solution = '';
        
        console.error('❌ Media error:', error);
        
        if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
            message = 'Camera and microphone access denied';
            solution = 'Please click "Allow" when prompted for camera/microphone permissions and refresh the page.';
        } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
            message = 'No camera or microphone found';
            solution = 'Please connect a camera and/or microphone to your computer and refresh the page.';
        } else if (error.name === 'NotReadableError' || error.name === 'TrackStartError') {
            message = 'Camera or microphone is already in use';
            solution = 'Please close other applications using your camera/microphone and refresh the page.';
        } else if (error.name === 'OverconstrainedError' || error.name === 'ConstraintNotSatisfiedError') {
            message = 'Camera or microphone settings not supported';
            solution = 'Your device does not support the required media settings. Please try with a different device.';
        } else if (error.name === 'SecurityError') {
            message = 'Security error accessing media devices';
            solution = 'Please ensure you are using HTTPS and your browser supports media access.';
        } else if (error.name === 'AbortError') {
            message = 'Media access was aborted';
            solution = 'Please try again and allow access to your camera and microphone.';
        } else {
            message = `Media access error: ${error.message || error.name || 'Unknown error'}`;
            solution = 'Please check your camera and microphone connections and refresh the page.';
        }
        
        this.updateConnectionStatus(message, 'error');
        this.showError(`${message}. ${solution}`);
        
        // Set media states to disabled
        this.isAudioEnabled = false;
        this.isVideoEnabled = false;
        this.updateAllMediaButtons();
        this.updateVideoPlaceholder();
        
        // Show a helpful message to user about the specific issue
        console.log('💡 Troubleshooting suggestions:');
        console.log('1. Check browser permissions for camera/microphone');
        console.log('2. Ensure no other applications are using the camera/microphone');
        console.log('3. Try refreshing the page');
        console.log('4. Check if camera/microphone is properly connected');
    }
    
    handleDisconnection() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            this.updateConnectionStatus(`Reconnecting... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`, 'warning');
            
            setTimeout(() => {
                if (this.socket) {
            try { this.socket.connect(); } catch (_) {}
                }
            }, 2000 * this.reconnectAttempts);
        } else {
            this.showError('Failed to reconnect. Please refresh the page.');
        }
    }
    
    handleConnectionError() {
        this.updateConnectionStatus('Connection error - retrying...', 'error');
    }

    restoreLocalState() {
        try {
            const raw = localStorage.getItem(this.persistKey);
            if (!raw) return;
            const state = JSON.parse(raw);
            this.isAudioEnabled = state.isAudioEnabled ?? this.isAudioEnabled;
            this.isVideoEnabled = state.isVideoEnabled ?? this.isVideoEnabled;
            this.wasInCallBeforeDisconnect = state.isInCall || false;
        } catch (e) {
            console.warn('Failed to restore local state:', e);
        }
    }

    persistLocalState() {
        try {
            localStorage.setItem(this.persistKey, JSON.stringify({
                isAudioEnabled: this.isAudioEnabled,
                isVideoEnabled: this.isVideoEnabled,
                isInCall: this.isInCall
            }));
        } catch (_) {}
    }

    installNavigationGuards() {
        if (this._navGuardsInstalled) return;
        this._navGuardsInstalled = true;

        // Warn on refresh/close
        this._beforeUnloadHandler = (e) => {
            if (this.isInCall) {
                e.preventDefault();
                e.returnValue = '';
            }
        };
        window.addEventListener('beforeunload', this._beforeUnloadHandler);

        // Intercept internal link clicks
        this._linkClickHandler = (e) => {
            const a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
            if (!a) return;
            if (a.hasAttribute('download')) return;
            if (a.getAttribute('href')?.startsWith('#')) return;
            if (a.target && a.target !== '_self') return;
            const href = a.getAttribute('href');
            if (!href) return;
            let url;
            try { url = new URL(href, window.location.href); } catch (_) { return; }
            if (url.origin !== window.location.origin) return;
            if (this.isInCall) {
                e.preventDefault();
                e.stopPropagation();
                if (window.NavGuardModal) {
                    window.NavGuardModal.open(url.href);
                } else {
                    if (confirm("You're in a call. Leave this page?")) window.location.href = url.href;
                }
            }
        };
        document.addEventListener('click', this._linkClickHandler, true);

        // Intercept form submissions
        this._formSubmitHandler = (e) => {
            if (this.isInCall) {
                e.preventDefault();
                e.stopPropagation();
                const form = e.target;
                if (window.NavGuardModal) {
                    window.NavGuardModal.open(null, () => form.submit());
                } else {
                    if (confirm("You're in a call. Submit and leave this page?")) form.submit();
                }
            }
        };
        document.addEventListener('submit', this._formSubmitHandler, true);

        // Guard history navigations
        this._origPushState = history.pushState.bind(history);
        this._origReplaceState = history.replaceState.bind(history);
        const self = this;
        history.pushState = function(...args) {
            if (self.isInCall) {
                if (window.NavGuardModal) {
                    window.NavGuardModal.open(null, () => self._origPushState(...args));
                    return;
                } else if (!confirm("You're in a call. Continue navigation?")) {
                    return;
                }
            }
            return self._origPushState(...args);
        };
        history.replaceState = function(...args) {
            if (self.isInCall) {
                if (window.NavGuardModal) {
                    window.NavGuardModal.open(null, () => self._origReplaceState(...args));
                    return;
                } else if (!confirm("You're in a call. Continue navigation?")) {
                    return;
                }
            }
            return self._origReplaceState(...args);
        };
        this._popStateHandler = () => {
            if (this.isInCall) {
                if (window.NavGuardModal) {
                    // Revert the navigation unless user confirms
                    window.NavGuardModal.open(null, () => {/* allow staying on new page */});
                    // If user cancels, we push forward to remain
                    const cancelBtn = document.getElementById('navGuardCancel');
                    if (cancelBtn) {
                        const handler = () => { history.forward(); cancelBtn.removeEventListener('click', handler); };
                        cancelBtn.addEventListener('click', handler, { once: true });
                    }
                } else if (!confirm("You're in a call. Leave this page?")) {
                    history.forward();
                }
            }
        };
        window.addEventListener('popstate', this._popStateHandler);
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
                video: {
                    deviceId: { exact: deviceId },
                    width: { ideal: 1920 },
                    height: { ideal: 1080 },
                    frameRate: { ideal: 30, max: 30 }
                },
                audio: false
            });
            
            // Replace video track
            const newVideoTrack = newStream.getVideoTracks()[0];
            this.localStream.removeTrack(videoTrack);
            this.localStream.addTrack(newVideoTrack);
            // Try to apply constraints to the new track as well
            try { await newVideoTrack.applyConstraints({ width: { ideal: 1920 }, height: { ideal: 1080 }, frameRate: { ideal: 30, max: 30 } }); } catch (_) {}
            
            // Update peer connection
            if (this.peerConnection) {
                const sender = this.peerConnection.getSenders().find(s => 
                    s.track && s.track.kind === 'video'
                );
                if (sender) {
                    await sender.replaceTrack(newVideoTrack);
                    // Re-apply high-quality params after track switch
                    try { await this.applyHighQualitySenderParams(); } catch (_) {}
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
        // Immediately reflect remote camera state in UI
        const remoteVideo = document.getElementById('remoteVideo');
        const remotePlaceholder = document.getElementById('remoteVideoPlaceholder');
        if (remoteVideo && remotePlaceholder) {
            if (data.video_enabled) {
                // Re-attach current remote stream if needed and ensure playback
                if (this.remoteStream && remoteVideo.srcObject !== this.remoteStream) {
                    try { remoteVideo.srcObject = this.remoteStream; } catch (_) {}
                }
                try { remoteVideo.autoplay = true; remoteVideo.playsInline = true; } catch (_) {}
                remoteVideo.classList.remove('hidden');
                remotePlaceholder.classList.add('hidden');
                const tryPlay = () => {
                    remoteVideo.play().catch(() => {
                        // No audio from remote video element usually; just retry silently
                    });
                };
                if (remoteVideo.readyState >= 2) tryPlay();
                remoteVideo.onloadedmetadata = () => tryPlay();
            } else {
                remoteVideo.classList.add('hidden');
                remotePlaceholder.classList.remove('hidden');
            }
        }
    }
    
    handleCounselorDisconnect() {
        this.showNotification('Counselor has left the session', 'warning');
        this.updateConnectionStatus('Waiting for counselor to return...', 'warning');
    }
    
    handleConnectionIssue() {
        this.showNotification('Connection issues detected. Trying to reconnect...', 'warning');
        this.updateConnectionStatus('Connection unstable - attempting to reconnect', 'warning');
    }

    // Auto-rejoin flow after socket reconnect
    async onSocketReconnected() {
        try {
            this.updateConnectionStatus('Reconnected. Restoring session…', 'info');
            this.joinSession();
            if (this.wasInCallBeforeDisconnect || this.isInCall) {
                // Ensure media ready
                if (!this.localStream) {
                    await this.initializeMedia();
                }
                // Always rebuild the PC on reconnect to avoid stale transceivers/senders
                await this.rebuildPeerConnection('socket_reconnect');
                // Also join call again to re-mark state and request renegotiation
                this.socket.emit('join_call', { session_id: this.sessionId });
                this.socket.emit('reconnect_request', { session_id: this.sessionId });
            }
        } catch (e) {
            console.warn('Failed to restore session on reconnect:', e);
        }
    }
    
    monitorConnectionQuality() {
    if (!this.peerConnection) return;
    if (this._qualityInterval) { clearInterval(this._qualityInterval); this._qualityInterval = null; }
    this._qualityInterval = setInterval(async () => {
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
        // Update UI indicators
        const qualityElement = document.getElementById('connectionQuality');
        if (qualityElement) {
            qualityElement.textContent = quality.charAt(0).toUpperCase() + quality.slice(1);
            qualityElement.className = `connection-${quality}`;
        }
        // Adapt outbound bitrate for varying network conditions on student side as well
        this.applyAdaptiveBitrate(quality).catch(() => {});
    }

    async applyAdaptiveBitrate(quality) {
        if (!this.peerConnection) return;
        const sender = this.peerConnection.getSenders()?.find(s => s.track && s.track.kind === 'video');
        if (!sender) return;
        const params = sender.getParameters() || {};
        params.degradationPreference = 'maintain-framerate';
        let maxBitrate, maxFramerate, scaleResolutionDownBy;
        switch (quality) {
            case 'poor':
                maxBitrate = 350_000; // ~350 kbps for constrained mobile data
                maxFramerate = 20;
                scaleResolutionDownBy = 2.0;
                break;
            case 'good':
                maxBitrate = 1_200_000; // ~1.2 Mbps typical Wi‑Fi
                maxFramerate = 30;
                scaleResolutionDownBy = 1.2;
                break;
            case 'excellent':
            default:
                maxBitrate = 2_500_000; // ~2.5 Mbps high quality
                maxFramerate = 30;
                scaleResolutionDownBy = 1.0;
        }
        params.encodings = [{ maxBitrate, maxFramerate, scaleResolutionDownBy }];
        try { await sender.setParameters(params); } catch (_) {}
    }

    scheduleConnectionRecovery(isFailed = false) {
        if (this._recoveryTimer) return;
        const delay = isFailed ? 2000 : 4000;
        this._recoveryTimer = setTimeout(async () => {
            this._recoveryTimer = null;
            try {
                if (!this.isInCall) return;
                if (!this.peerConnection) return;
                const state = this.peerConnection.connectionState;
                if (state !== 'connected') {
                    await this.rebuildPeerConnection('auto_recovery');
                    // Ask peer to renegotiate
                    this.socket.emit('reconnect_request', { session_id: this.sessionId });
                }
            } catch (e) {
                console.warn('Student recovery attempt failed:', e);
            }
        }, delay);
    }

    async rebuildPeerConnection(reason = 'manual') {
        console.log('Rebuilding RTCPeerConnection (student) due to:', reason);
        try {
            this.reconnectInProgress = true;
            const oldPc = this.peerConnection;
            if (oldPc) {
                try { oldPc.ontrack = null; oldPc.onicecandidate = null; oldPc.onconnectionstatechange = null; oldPc.oniceconnectionstatechange = null; } catch (_) {}
                try { oldPc.close(); } catch (_) {}
            }
            this.peerConnection = null;
            // Create fresh PC and re-add local tracks
            await this.createPeerConnection();
            // Student normally waits for counselor offer; request renegotiation explicitly
            this.socket.emit('reconnect_request', { session_id: this.sessionId });
        } catch (e) {
            console.warn('Failed to rebuild peer connection (student):', e);
        } finally {
            setTimeout(() => { this.reconnectInProgress = false; }, 1500);
        }
    }
    
    // Screen sharing handlers
    handleScreenShareStarted(data) {
        console.log('🖥️ Handling screen share started from counselor');
        
        // The remote video will automatically update when the counselor replaces their video track
        // Ensure the element is optimized for screens and playback starts
        const remoteVideo = document.getElementById('remoteVideo');
        if (remoteVideo) {
            remoteVideo.style.objectFit = 'contain'; // Better for screen content
            if (this.remoteStream) {
                remoteVideo.srcObject = this.remoteStream;
            }
            const tryPlay = () => {
                remoteVideo.play().catch(e => {
                    console.warn('Remote video play (screen share start) blocked:', e?.name || e);
                });
            };
            remoteVideo.onloadedmetadata = () => tryPlay();
            if (remoteVideo.readyState >= 2) tryPlay();
            console.log('✅ Remote video set to contain mode for screen sharing');
        }
        
        // Update UI to show screen sharing indicator
        this.showScreenShareIndicator(true);
        
        // Show notification to student
        this.showNotification('Counselor is now sharing their screen', 'info');
    }
    
    handleScreenShareStopped(data) {
        console.log('🛑 Handling screen share stopped from counselor');
        
        // Reset remote video display and ensure playback resumes
        const remoteVideo = document.getElementById('remoteVideo');
        if (remoteVideo) {
            remoteVideo.style.objectFit = 'cover'; // Back to normal video mode
            console.log('✅ Remote video set back to cover mode');
            if (this.remoteStream) {
                remoteVideo.srcObject = this.remoteStream;
            }
            const tryPlay = () => {
                remoteVideo.play().catch(e => console.warn('Remote video play (screen share stop) blocked:', e?.name || e));
            };
            remoteVideo.onloadedmetadata = () => tryPlay();
            if (remoteVideo.readyState >= 2) tryPlay();
        }
        
        // Hide screen sharing indicator
        this.showScreenShareIndicator(false);
        
        // Show notification to student
        this.showNotification('Screen sharing ended', 'info');
    }
    
    showScreenShareIndicator(isSharing) {
        // Add a visual indicator for screen sharing
        let indicator = document.getElementById('screenShareIndicator');
        
        if (isSharing) {
            if (!indicator) {
                indicator = document.createElement('div');
                indicator.id = 'screenShareIndicator';
                indicator.className = 'absolute top-4 left-4 bg-blue-600 text-white px-3 py-1 rounded-full text-sm font-medium flex items-center space-x-2 z-20';
                indicator.innerHTML = `
                    <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M3 4a1 1 0 011-1h12a1 1 0 011 1v8a1 1 0 01-1 1H4a1 1 0 01-1-1V4zm1 0v8h12V4H4z" clip-rule="evenodd"></path>
                        <path d="M5 16a1 1 0 011-1h8a1 1 0 110 2H6a1 1 0 01-1-1z"></path>
                    </svg>
                    <span>Screen Sharing</span>
                `;
                
                // Add to remote video container
                const remoteVideoContainer = document.getElementById('remoteVideoContainer') || document.getElementById('mainVideoContainer');
                if (remoteVideoContainer) {
                    remoteVideoContainer.appendChild(indicator);
                    console.log('✅ Screen share indicator added');
                }
            }
        } else {
            if (indicator) {
                indicator.remove();
                console.log('✅ Screen share indicator removed');
            }
        }
    }
    
    showRecordingIndicator(isRecording) {
        // Add a visual indicator for recording
        let indicator = document.getElementById('recordingIndicator');
        
        if (isRecording) {
            if (!indicator) {
                indicator = document.createElement('div');
                indicator.id = 'recordingIndicator';
                indicator.className = 'absolute top-4 right-4 bg-red-600 text-white px-3 py-1 rounded-full text-sm font-medium flex items-center space-x-2 z-20 animate-pulse';
                indicator.innerHTML = `
                    <div class="w-3 h-3 bg-red-400 rounded-full animate-pulse"></div>
                    <span>Recording</span>
                `;
                
                // Add to video container
                const videoContainer = document.getElementById('callUI') || document.body;
                if (videoContainer) {
                    videoContainer.appendChild(indicator);
                    console.log('✅ Recording indicator added');
                }
            }
        } else {
            if (indicator) {
                indicator.remove();
                console.log('✅ Recording indicator removed');
            }
        }
    }
    
    handleRemoteAudioToggle(data) {
        console.log('Remote audio toggle:', data);
        // Could add visual indicator for remote audio state
        const message = data.audio_enabled ? 
            `${data.name} turned on microphone` : 
            `${data.name} turned off microphone`;
        this.showNotification(message, 'info');
    }
    
    handleRemoteVideoToggle(data) {
        console.log('Remote video toggle:', data);
        // Immediately reflect remote camera state in UI
        const remoteVideo = document.getElementById('remoteVideo');
        const remotePlaceholder = document.getElementById('remoteVideoPlaceholder');
        if (remoteVideo && remotePlaceholder) {
            if (data.video_enabled) {
                remoteVideo.classList.remove('hidden');
                remotePlaceholder.classList.add('hidden');
                if (remoteVideo.readyState >= 2) {
                    remoteVideo.play().catch(() => {});
                }
            } else {
                remoteVideo.classList.add('hidden');
                remotePlaceholder.classList.remove('hidden');
            }
        }
        const message = data.video_enabled ? 
            `${data.name} turned on camera` : 
            `${data.name} turned off camera`;
        this.showNotification(message, 'info');
    }
    
    handleSessionEnd(data) {
        console.log('Session ended:', data);
        this.stopSessionTimer();
        this.showNotification(`Session ended by ${data.ended_by}`, 'info');
        this.updateConnectionStatus('Session has ended', 'info');
        this.cleanup();
        
        setTimeout(() => {
            window.location.href = '/student/dashboard';
        }, 3000);
    }
    
    handleCounselorDisconnect() {
        console.log('Counselor disconnected');
        this.showNotification('Counselor has disconnected from the session', 'warning');
        this.updateConnectionStatus('Waiting for counselor to reconnect...', 'warning');
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
    
    async retryWithBasicConstraints() {
        console.log('Retrying with basic media constraints...');
        try {
            const basicConstraints = {
                video: true,
                audio: true
            };
            
            this.localStream = await navigator.mediaDevices.getUserMedia(basicConstraints);
            console.log('Basic media access granted');
            
            // Attach to video elements
            const waitingRoomVideo = document.getElementById('waitingRoomVideo');
            if (waitingRoomVideo) {
                waitingRoomVideo.srcObject = this.localStream;
                waitingRoomVideo.muted = true;
                
                waitingRoomVideo.onloadedmetadata = () => {
                    waitingRoomVideo.play().catch(e => {
                        console.warn('Error playing waiting room video after retry:', e);
                    });
                };
            }
            
            const localVideo = document.getElementById('localVideo');
            if (localVideo) {
                localVideo.srcObject = this.localStream;
                localVideo.muted = true;
                
                localVideo.onloadedmetadata = () => {
                    localVideo.play().catch(e => {
                        console.warn('Error playing local video after retry:', e);
                    });
                };
            }
            
            this.isAudioEnabled = true;
            this.isVideoEnabled = true;
            
            // Populate device list after successful retry
            await this.populateDeviceList();
            
            this.updateAllMediaButtons();
            this.updateVideoPlaceholder();
            this.updateConnectionStatus('Camera and microphone ready (basic mode)', 'success');
            
        } catch (retryError) {
            console.error('Failed to access media with basic constraints:', retryError);
            this.handleMediaError(retryError);
        }
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