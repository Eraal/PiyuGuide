// Video Counseling WebSocket Client for Office/Counselor
console.log("Video Counseling WebSocket Client for Office/Counselor");

class VideoCounselingClientOffice {
    constructor(sessionId, userId, userName) {
        this.sessionId = sessionId;
        this.userId = userId;
        this.userName = userName;
        this.socket = null;
        this.peerConnection = null;
        this.localStream = null;
        this.remoteStream = null;
        this.screenShareStream = null;
        this.isAudioEnabled = true;
        this.isVideoEnabled = true;
        this.isScreenSharing = false;
    this.isRecording = false; // recording disabled
        this.isConnected = false;
    this.sessionTimer = null;
    this.startTime = null; // legacy, not authoritative
    this.sessionStartAt = null; // authoritative from server
    // Recording support
    this.mediaRecorder = null;
    this.recordedChunks = [];
        this.isInCall = false;
        this.heartbeatInterval = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.connectionQuality = 'unknown';
        this.sessionNotes = '';
    this.reconnectInProgress = false;
    this.wasInCallBeforeDisconnect = false;
    this.persistKey = `videoCounseling:${this.sessionId}:${this.userId}`;
    this.pendingIceCandidates = [];
    this._recoveryTimer = null;
    // Perfect negotiation/glare-handling + restart debounce
    this.isMakingOffer = false;
    this.polite = true; // Office acts as polite peer to reduce glare failures
    this._lastIceRestartAt = 0;
    this._lastOfferAt = 0; // track last local offer timestamp
    this._preferH264 = this._getPref('webrtc.preferH264', true);
        
        // ICE servers configuration (prefer server-injected config)
        // LAN-only mode: Empty array = direct peer-to-peer on local network
        const injectedIce = (typeof window !== 'undefined' && Array.isArray(window.PG_ICE_SERVERS)) ? window.PG_ICE_SERVERS : null;
        const isLanOnly = (typeof window !== 'undefined' && window.PG_LAN_ONLY_MODE === true);
        
        if (isLanOnly || (injectedIce && injectedIce.length === 0)) {
            // LAN-only mode: No external STUN/TURN needed
            this.iceServers = [];
            console.log('[VideoCounseling][Office] LAN-only mode enabled - direct peer connection');
        } else if (injectedIce && injectedIce.length > 0) {
            this.iceServers = injectedIce;
        } else {
            // Fallback to public STUN servers (requires internet)
            this.iceServers = [
                { urls: 'stun:stun.l.google.com:19302' },
                { urls: 'stun:stun1.l.google.com:19302' },
                { urls: 'stun:stun2.l.google.com:19302' }
            ];
            console.warn('[VideoCounseling][Office] Using public STUN servers - requires internet connection');
        }
        
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
            console.log('🚀 Initializing Video Counseling Client for Office...');
            this.restoreLocalState();
            this.initializeSocket();
            this.setupEventListeners();
            this.installNavigationGuards();
            await this.initializeMedia();
            await this.populateDeviceList();
            this.showWaitingRoom();
            this.initChat();
            this.initNotes();
            this.initPipDrag();
        } catch (error) {
            console.error('Failed to initialize video counseling:', error);
            this.showError('Failed to initialize video calling. Please refresh and try again.');
        }
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
                    window.NavGuardModal.open(null, () => {/* allow staying on new page */});
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

        // Peer requests renegotiation after they reconnect
        this.socket.on('reconnect_request', async (data) => {
            console.log('Peer requested reconnection/renegotiation:', data);
            try {
                    // Prefer rebuilding the peer connection to ensure fresh transceivers/tracks
                    if (this.isInCall) {
                        await this.rebuildPeerConnection('peer_reconnect_request');
                    } else if (this.peerConnection) {
                        await this.createAndSendOffer({ iceRestart: true });
                    }
            } catch (e) {
                console.warn('Failed to renegotiate on reconnect_request:', e);
            }
        });
        
        this.socket.on('connect_error', (error) => {
            console.error('Connection error:', error);
            this.updateConnectionStatus('Connection error', 'error');
            this.handleConnectionError();
        });
        
        this.socket.on('call_started', (data) => {
            console.log('Call started (live):', data);
            if (data && data.started_at) {
                try {
                    this.sessionStartAt = new Date(data.started_at);
                    this.ensureSessionTimerRunning();
                } catch (_) {}
            }
        });
        
        this.socket.on('session_joined', (data) => {
            console.log('Successfully joined session:', data);
            this.updateWaitingRoomMessage('Waiting for student to join...');
            if (data && data.started_at) {
                try { this.sessionStartAt = new Date(data.started_at); this.ensureSessionTimerRunning(); } catch (_) {}
            }
            
            // Check if student is already present
            const studentPresent = data.participants.some(p => p.role === 'student');
            
            if (studentPresent) {
                this.updateWaitingRoomMessage('Student is present. Getting ready...');
                this.updateConnectionStatus('Student detected - both users present', 'success');
                this.updateParticipantIndicators(true, true);
                this.socket.emit('ready', { session_id: this.sessionId });
            } else {
                this.updateConnectionStatus('Connected - waiting for student', 'warning');
                this.updateParticipantIndicators(true, false);
            }
        });
        
        this.socket.on('user_joined', (data) => {
            console.log('User joined session:', data);
            if (data.role === 'student') {
                this.updateWaitingRoomMessage('Student has joined. Getting ready...');
                this.updateConnectionStatus('Student joined - both users present', 'success');
                this.updateParticipantIndicators(true, true);
                
                // Restore dual-participant layout
                const callInterface = document.getElementById('vcCall');
                if (callInterface) callInterface.classList.remove('single-user');
                
                this.socket.emit('ready', { session_id: this.sessionId });
            }
        });
        
        this.socket.on('user_ready', (data) => {
            console.log('User ready:', data);
            if (data.role === 'student') {
                this.updateWaitingRoomMessage('Student is ready. Preparing call...');
                this.updateConnectionStatus('Both users ready - call can start', 'success');
                // Ensure the Start Call button is shown as soon as the student is ready
                this.showStartCallButton();
            }
        });
        
        this.socket.on('session_ready', (data) => {
            console.log('Session is ready to start:', data);
            this.updateConnectionStatus('Ready to start call', 'success');
            this.showStartCallButton();
        });
        // Handle call starting
        this.socket.on('call_starting', (data) => {
            console.log('Call is starting:', data);
        });

        // Apply initial media state for other participants
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

    // Connection quality updates
    this.socket.on('quality_update', (data) => this.updateConnectionQuality(data.quality));
        
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
                await this.handleAnswer(data.answer, data.offer_id);
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
        
        this.socket.on('session_ended', (data) => {
            console.log('Session ended by:', data.ended_by);
            this.handleSessionEnd(data);
        });
        
        this.socket.on('user_left', (data) => {
            console.log('User left session:', data);
            if (data.role === 'student') {
                this.updateConnectionStatus('Student has left the session. You can wait for them to reconnect.', 'info');
                this.updateParticipantIndicators(true, false);
                // Update UI to show waiting state
                const qText = document.getElementById('vcQualityText');
                const qDot = document.getElementById('vcQualityDot');
                if (qText) qText.textContent = 'Student Left';
                if (qDot) qDot.className = 'vc-quality-dot fair';
                
                // Switch to single user layout
                const callInterface = document.getElementById('vcCall');
                if (callInterface) callInterface.classList.add('single-user');
            }
        });
        
        this.socket.on('quality_update', (data) => {
            this.updateConnectionQuality(data.quality);
        });
        
        this.socket.on('notes_saved', (data) => {
            if (data.success) {
                this.showNotification('Notes saved successfully', 'success');
            }
        });

        // Recording events removed
        
        this.socket.on('error', (data) => {
            console.error('Server error:', data.message);
            this.showError(data.message);
        });
        
        this.socket.on('heartbeat_ack', () => {
            // Heartbeat acknowledged
        });
    }
    
async handleIceCandidate(candidate) {
        console.log('Handling ICE candidate');
        
        if (this.peerConnection && this.peerConnection.remoteDescription) {
            try {
                if (!candidate) return; // Skip null end-of-candidates
                if (!this.peerConnection || !this.peerConnection.remoteDescription) {
                    // Queue until remote description is set
                    this.pendingIceCandidates.push(candidate);
                    return;
                }
                await this.peerConnection.addIceCandidate(candidate);
                console.log('ICE candidate added successfully');
            } catch (error) {
                console.error('Error adding ICE candidate:', error);
            }
        } else {
            console.warn('Cannot add ICE candidate - peer connection not ready or no remote description');
        }
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
            
            // Try to enhance local media quality (1080p@30fps, higher bitrate)
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
        // In-call mic/camera toggles
        const micToggle = document.getElementById('micToggle');
        if (micToggle) micToggle.addEventListener('click', () => this.toggleAudio());
        const camToggle = document.getElementById('camToggle');
        if (camToggle) camToggle.addEventListener('click', () => this.toggleVideo());

        // Lobby mic/camera toggles
        const lobbyMic = document.getElementById('lobbyMicBtn');
        if (lobbyMic) lobbyMic.addEventListener('click', () => this.toggleAudio(true));
        const lobbyCam = document.getElementById('lobbyCamBtn');
        if (lobbyCam) lobbyCam.addEventListener('click', () => this.toggleVideo(true));

        // Screen share
        const screenBtn = document.getElementById('screenShareBtn');
        if (screenBtn) screenBtn.addEventListener('click', () => this.toggleScreenShare());

        // End call
        const endCallBtn = document.getElementById('endCallBtn');
        if (endCallBtn) endCallBtn.addEventListener('click', () => this.showEndSessionModal());

        // Join / Start call
        const joinCallBtn = document.getElementById('joinCallBtn');
        if (joinCallBtn) joinCallBtn.addEventListener('click', () => { this.startCall(); });

        // Fullscreen
        const fsBtn = document.getElementById('fullscreenBtn');
        if (fsBtn) fsBtn.addEventListener('click', () => this.toggleFullScreen());

        // Modal controls
        const confirmEndBtn = document.getElementById('confirmEndBtn');
        if (confirmEndBtn) confirmEndBtn.addEventListener('click', () => this.endSession());
        const cancelEndBtn = document.getElementById('cancelEndBtn');
        if (cancelEndBtn) cancelEndBtn.addEventListener('click', () => this.hideEndSessionModal());
        const modal = document.getElementById('endSessionModal');
        if (modal) modal.addEventListener('click', (e) => { if (e.target === modal) this.hideEndSessionModal(); });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'F11') { e.preventDefault(); this.toggleFullScreen(); }
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
        console.log('=== COUNSELOR STARTING VIDEO CALL ===');
        console.log('Session ID:', this.sessionId);
        console.log('Is in call before:', this.isInCall);
        
        try {
            // Office is authoritative for start time: tell server we're starting the call
            if (this.socket) {
                this.socket.emit('start_call', { session_id: this.sessionId });
            }
            await this.createPeerConnection();
            console.log('Peer connection created successfully');
            
            // Don't show call UI immediately - wait for connection to establish
            // Timer will be based on server started_at from call_starting/call_joined
            this.isInCall = true;
            console.log('Is in call after:', this.isInCall);
            // Mark ourselves as in-call for server-side state
            if (this.socket) {
                this.socket.emit('join_call', { session_id: this.sessionId });
            }

            // Create and send offer (with codec preference + glare safety)
            await this.createAndSendOffer();
            console.log('Offer created and sent');

            this.updateConnectionStatus('Call started - waiting for student response', 'info');
            
        } catch (error) {
            console.error('Error starting call:', error);
            this.showError('Failed to start video call');
        }
        
        console.log('=== START CALL COMPLETED ===');
    }
    
    async createPeerConnection() {
        console.log('Creating peer connection...');
        
        // Allow forcing relay-only via URL param ?relay=1 for debugging restrictive networks
        const params = new URLSearchParams(window.location.search);
        const forceRelay = params.get('relay') === '1';
        this.peerConnection = new RTCPeerConnection({
            iceServers: this.iceServers,
            iceTransportPolicy: forceRelay ? 'relay' : 'all',
            bundlePolicy: 'balanced'
        });
    // Proactively ensure we can receive remote media immediately
    try { this.ensureReceiveTransceivers(); } catch (_) {}
        
        // Ensure we have recvonly transceivers BEFORE adding local tracks so we can receive student media immediately
        try {
            const existing = this.peerConnection.getTransceivers ? this.peerConnection.getTransceivers() : [];
            if (!existing || existing.length === 0) {
                try { this.peerConnection.addTransceiver('video', { direction: 'recvonly' }); } catch (_) {}
                try { this.peerConnection.addTransceiver('audio', { direction: 'recvonly' }); } catch (_) {}
            }
        } catch (_) {}

        // Add local stream tracks
        if (this.localStream) {
            this.localStream.getTracks().forEach(track => {
                try {
                    this.peerConnection.addTrack(track, this.localStream);
                } catch (e) {
                    console.warn('addTrack failed (office):', e?.name || e);
                }
            });
        }
        // Ensure we maintain recv capability regardless of local tracks
        this.ensureReceiveTransceivers();
        // Try to boost outbound video quality
        try {
            await this.applyHighQualitySenderParams();
        } catch (e) {
            console.warn('Could not set high-quality sender params:', e?.name || e);
        }
        
        // Handle remote stream
        this.peerConnection.ontrack = (event) => {
            console.log('Received remote stream from student');
            this.remoteStream = event.streams[0];
            const remoteVideo = document.getElementById('remoteVideo');
            const remotePlaceholder = document.getElementById('remoteVideoPlaceholder');
            if (remoteVideo) {
                remoteVideo.srcObject = this.remoteStream;
                // Reinforce autoplay/inline and visibility
                try { remoteVideo.autoplay = true; remoteVideo.playsInline = true; } catch (_) {}
                try { remoteVideo.classList.remove('hidden'); if (remotePlaceholder) remotePlaceholder.classList.add('hidden'); } catch(_) {}
                // Apply letterboxing containment by default and adjust for portrait
                try {
                    remoteVideo.style.objectFit = 'contain';
                    remoteVideo.style.backgroundColor = '#000';
                    const t = event.track;
                    const s = t && t.getSettings ? t.getSettings() : null;
                    if (s && s.width && s.height) {
                        if (s.height > s.width) {
                            remoteVideo.style.objectFit = 'contain';
                        }
                    }
                } catch (_) {}

                const tryPlay = (attempt = 'initial') => {
                    const doPlay = () => remoteVideo.play().catch(e => {
                        console.warn(`Remote video play blocked (${attempt}):`, e?.name || e);
                        // Fallback: try muted autoplay, then unmute on first user interaction
                        if (!remoteVideo.muted) {
                            remoteVideo.muted = true;
                            remoteVideo.play().catch(() => {});
                            this._awaitFirstUserGestureToUnmute(remoteVideo);
                        }
                    });
                    // If metadata is ready, attempt immediately
                    if (remoteVideo.readyState >= 2) doPlay(); else doPlay();
                };
                remoteVideo.onloadedmetadata = () => tryPlay();
                if (remoteVideo.readyState >= 2) tryPlay();
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

        this.peerConnection.onicegatheringstatechange = () => {
            console.debug('[Office] ICE gathering state:', this.peerConnection.iceGatheringState);
        };

        // Log selected candidate pair for debugging TURN usage
        try {
            this.peerConnection.addEventListener('connectionstatechange', async () => {
                if (this.peerConnection.connectionState === 'connected') {
                    try {
                        const stats = await this.peerConnection.getStats();
                        stats.forEach(report => {
                            if (report.type === 'candidate-pair' && report.nominated) {
                                const local = stats.get(report.localCandidateId);
                                const remote = stats.get(report.remoteCandidateId);
                                console.log('[Office] Selected candidate pair:', {
                                    transport: report.transportId && stats.get(report.transportId)?.dtlsState,
                                    local: local ? { type: local.candidateType, protocol: local.protocol, address: local.address, port: local.port } : null,
                                    remote: remote ? { type: remote.candidateType, protocol: remote.protocol, address: remote.address, port: remote.port } : null
                                });
                            }
                        });
                    } catch (_) {}
                }
            });
        } catch (_) {}

        // Safe renegotiation on need
        this.peerConnection.onnegotiationneeded = async () => {
            try {
                if (!this.isInCall) return;
                await this.createAndSendOffer();
            } catch (e) {
                console.warn('Negotiationneeded offer failed:', e?.name || e);
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
                    // Force the connection quality indicator to show Connected
                    const qText = document.getElementById('vcQualityText');
                    const qDot = document.getElementById('vcQualityDot');
                    if (qText) qText.textContent = 'Connected';
                    if (qDot) qDot.className = 'vc-quality-dot good';
                    
                    // Remove single user mode if we are connected
                    const callInterface = document.getElementById('vcCall');
                    if (callInterface) callInterface.classList.remove('single-user');
                    
                    // Tell server we are actively connected to start the official timer
                    if (this.socket) {
                        this.socket.emit('call_connected', { session_id: this.sessionId });
                    }
                    
                    // Ensure call UI is shown when connected
                    if (this.isInCall) {
                        this.showCallUI();
                    }
                    // Clear any scheduled recovery when connected
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
        const maxBitrate = 2500_000; // ~2.5 Mbps target
        const maxFr = 30;
        params.encodings = [{ maxBitrate, maxFramerate: maxFr, scaleResolutionDownBy: 1 }];
        try {
            await sender.setParameters(params);
        } catch (e) {
            console.debug('setParameters failed (non-fatal):', e?.name || e);
        }
    }

    async enhanceLocalMediaQuality(context = 'manual') {
        if (!this.localStream) return;
        const vt = this.localStream.getVideoTracks()[0];
        if (!vt) return;
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
            // Debounce restarts to avoid glare storms
            const now = Date.now();
            if (now - this._lastIceRestartAt < 2000) {
                console.debug('Skipping ICE restart (debounced)');
                return;
            }
            this._lastIceRestartAt = now;
            this.reconnectInProgress = true;
            this.updateConnectionStatus('Re-establishing media path…', 'warning');
            this.ensureReceiveTransceivers();
            await this.createAndSendOffer({ iceRestart: true });
        } catch (e) {
            console.warn('ICE restart failed:', e);
        } finally {
            setTimeout(() => { this.reconnectInProgress = false; }, 1500);
        }
    }

    _getPref(key, defaultValue) {
        try {
            const v = localStorage.getItem(key);
            if (v === null || v === undefined) return defaultValue;
            if (v === '0' || v === 'false' || v === 'no') return false;
            if (v === '1' || v === 'true' || v === 'yes') return true;
            return defaultValue;
        } catch (_) { return defaultValue; }
    }

    async preferH264Codecs() {
        try {
            if (!this.peerConnection || !this.peerConnection.getTransceivers) return;
            const tvs = this.peerConnection.getTransceivers();
            const can = RTCRtpReceiver.getCapabilities ? RTCRtpReceiver.getCapabilities('video') : null;
            if (!can || !Array.isArray(can.codecs) || !tvs || tvs.length === 0) { this._supportsSetCodecPreferences = false; return; }
            const codecs = can.codecs;
            const h264Primary = codecs.filter(c => /h264/i.test(c.mimeType || c.name || '') && !/rtx/i.test(c.mimeType || ''));
            const h264Rtx = codecs.filter(c => /h264/i.test(c.mimeType || c.name || '') && /rtx/i.test(c.mimeType || ''));
            const others = codecs.filter(c => !/h264/i.test(c.mimeType || c.name || ''));
            const ordered = [...h264Primary, ...h264Rtx, ...others];
            tvs.forEach(t => {
                try {
                    if (t && t.setCodecPreferences && t.receiver && t.receiver.track && t.receiver.track.kind === 'video') {
                        t.setCodecPreferences(ordered);
                        this._supportsSetCodecPreferences = true;
                    }
                } catch (_) {}
            });
        } catch (_) { this._supportsSetCodecPreferences = false; }
    }

    mungeSdpPreferH264(sdp) {
        try {
            if (!sdp || typeof sdp !== 'string') return sdp;
            const lines = sdp.split('\r\n');
            const rtpmap = {};
            const h264Pts = new Set();
            for (const line of lines) {
                if (line.startsWith('a=rtpmap:')) {
                    const match = line.match(/^a=rtpmap:(\d+)\s+([^/]+)/);
                    if (match) {
                        const pt = match[1];
                        const codec = match[2];
                        rtpmap[pt] = codec;
                        if (/^H264$/i.test(codec)) h264Pts.add(pt);
                    }
                }
            }
            return sdp.replace(/(m=video \d+ [^ ]+ )([0-9 ]+)/, (m, prefix, pts) => {
                const parts = pts.trim().split(' ').filter(Boolean);
                const h264 = parts.filter(p => h264Pts.has(p));
                const non = parts.filter(p => !h264Pts.has(p));
                return prefix + [...h264, ...non].join(' ');
            });
        } catch (_) { return sdp; }
    }

    async createAndSendOffer(options = {}) {
        if (!this.peerConnection) return;
        try {
            this.isMakingOffer = true;
            this.ensureReceiveTransceivers();
            if (this._preferH264) {
                await this.preferH264Codecs();
            }
            let offer = await this.peerConnection.createOffer(options);
            if (this._preferH264 && !this._supportsSetCodecPreferences && offer && offer.sdp) {
                offer = new RTCSessionDescription({ type: offer.type, sdp: this.mungeSdpPreferH264(offer.sdp) });
            }
            await this.peerConnection.setLocalDescription(offer);
            this._lastOfferAt = Date.now();
            this.socket.emit('offer', {
                session_id: this.sessionId,
                offer: this.peerConnection.localDescription,
                target_user_id: null
            });
        } catch (e) {
            console.warn('Failed to create/send offer:', e?.name || e);
        } finally {
            this.isMakingOffer = false;
        }
    }

    ensureReceiveTransceivers() {
        try {
            if (!this.peerConnection || !this.peerConnection.getTransceivers) return;
            const transceivers = this.peerConnection.getTransceivers();
            const ensureKind = (kind) => {
                let haveRecv = false;
                transceivers.forEach(t => {
                    const dir = t?.direction || t?.currentDirection;
                    const rkind = t?.receiver?.track?.kind;
                    const skind = t?.sender?.track?.kind;
                    if ((rkind === kind || skind === kind)) {
                        if (typeof t.setDirection === 'function') {
                            try { t.setDirection('sendrecv'); } catch(_) {}
                        }
                        if (dir && (dir.includes('recv') || dir === 'sendrecv')) haveRecv = true;
                    }
                });
                if (!haveRecv) {
                    try { this.peerConnection.addTransceiver(kind, { direction: 'recvonly' }); } catch (e) { console.debug(`addTransceiver(${kind}) failed:`, e?.name || e); }
                }
            };
            ensureKind('video');
            ensureKind('audio');
        } catch (e) {
            console.debug('ensureReceiveTransceivers failed (non-fatal):', e?.name || e);
        }
    }

    _awaitFirstUserGestureToUnmute(videoEl) {
        if (!videoEl) return;
        if (this._unmuteHandlerInstalled) return;
        this._unmuteHandlerInstalled = true;
        const handler = () => {
            try { videoEl.muted = false; videoEl.play().catch(() => {}); } catch(_) {}
            window.removeEventListener('click', handler, true);
            window.removeEventListener('keydown', handler, true);
            this._unmuteHandlerInstalled = false;
        };
        window.addEventListener('click', handler, true);
        window.addEventListener('keydown', handler, true);
    }
    
    async handleOffer(offer) {
        console.log('Handling WebRTC offer');
        
        if (!this.peerConnection) {
            await this.createPeerConnection();
        }
        // Perfect negotiation: handle glare by rolling back if we're making an offer or not stable
        const pc = this.peerConnection;
        const offerCollision = this.isMakingOffer || (pc.signalingState !== 'stable');
        try {
            if (offerCollision) {
                if (!this.polite) {
                    console.warn('Offer collision (impolite) — ignoring incoming offer');
                    return;
                }
                try { await pc.setLocalDescription({ type: 'rollback' }); } catch (_) {}
            }
            await pc.setRemoteDescription(offer);
        } catch (e) {
            console.warn('Failed to set remote description (offer):', e?.name || e);
            return;
        }
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

    // Drain any ICE candidates that arrived before remote description
    this.drainPendingIceCandidates();
    }
    
    async handleAnswer(answer, offerId = null) {
        console.log('Handling WebRTC answer', offerId ? `(offerId=${offerId})` : '');

        if (!this.peerConnection) return;

        const pc = this.peerConnection;
        let state = pc.signalingState;
        console.log('Current signalingState before applying answer:', state);

        // Only apply remote answer if we are in the correct state
        if (state !== 'have-local-offer') {
            console.warn('Ignoring unexpected answer in state:', state);
            return;
        }

        try {
            // Re-check immediately to avoid race with auto-renegotiation
            state = pc.signalingState;
            if (state !== 'have-local-offer') {
                console.warn('State changed before applying answer, now:', state, '— ignoring answer');
                return;
            }
            await pc.setRemoteDescription(answer);
        } catch (e) {
            const msg = (e && (e.message || e.name)) || '';
            if (e?.name === 'InvalidStateError' || /Called in wrong state/i.test(msg)) {
                console.warn('Ignoring late/duplicate answer due to state change:', msg);
                return;
            }
            console.warn('Failed to set remote description (answer):', e?.name || e);
            return;
        }

        this.updateConnectionStatus('Call connection established', 'success');
        setTimeout(() => {
            console.log('Checking if we should show call UI...');
            console.log('isInCall:', this.isInCall);
            console.log('Connection state:', this.peerConnection?.connectionState);
            console.log('ICE state:', this.peerConnection?.iceConnectionState);
            if (this.isInCall) {
                this.showCallUI();
                const rv = document.getElementById('remoteVideo');
                if (rv) { try { rv.play().catch(() => {}); } catch(_) {} }
            }
        }, 500);
        this.drainPendingIceCandidates();
    }
    
    showCallUI() {
        console.log('=== SHOWING CALL UI (OFFICE) ===');
        const waitingRoom = document.getElementById('vcLobby');
        const callInterface = document.getElementById('vcCall');
        if (waitingRoom) waitingRoom.classList.add('hidden');
        if (callInterface) {
            callInterface.classList.add('active');
            // If the connection is not yet fully established, start in single-user mode
            if (!this.peerConnection || this.peerConnection.connectionState !== 'connected') {
                callInterface.classList.add('single-user');
            }
        }

        // Ensure local video stream is attached
        const localVideo = document.getElementById('localVideo');
        if (localVideo && this.localStream) {
            localVideo.srcObject = this.localStream;
            localVideo.muted = true;
        }

        this.updateAllMediaButtons();
        this.updateVideoPlaceholder();
        this.initControlsAutoHide();

        console.log('=== CALL UI SETUP COMPLETE ===');
    }

    requestFullscreenOnCallStart() {
        // Auto-use the in-app fullscreen styling only; do NOT invoke browser Fullscreen API here
        try {
            this.enterFullscreenMode();
        } catch (_) {}
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
                    // Notify waiting room media toggle
                    this.socket.emit('waiting_room_media_toggle', {
                        session_id: this.sessionId,
                        media_type: 'audio',
                        enabled: this.isAudioEnabled
                    });
                }
                
                // Update all media buttons (both waiting room and call interface)
                this.updateAllMediaButtons();
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
                    // Notify waiting room media toggle
                    this.socket.emit('waiting_room_media_toggle', {
                        session_id: this.sessionId,
                        media_type: 'video',
                        enabled: this.isVideoEnabled
                    });
                }
                
                // Update all media buttons (both waiting room and call interface)
                this.updateAllMediaButtons();
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

    async toggleScreenShare() {
        if (!this.isScreenSharing) {
            await this.startScreenShare();
        } else {
            await this.stopScreenShare();
        }
    }
    
    async startScreenShare() {
        try {
            console.log('🖥️ Starting screen share...');
            
            // Get screen capture stream with enhanced options
            this.screenShareStream = await navigator.mediaDevices.getDisplayMedia({
                video: {
                    mediaSource: 'screen',
                    width: { ideal: 1920, max: 1920 },
                    height: { ideal: 1080, max: 1080 },
                    frameRate: { ideal: 30, max: 30 }
                },
                audio: true
            });
            
            console.log('✅ Screen capture stream obtained');
            
            // Replace video track in peer connection
            if (this.peerConnection) {
                const videoSender = this.peerConnection.getSenders().find(sender => 
                    sender.track && sender.track.kind === 'video'
                );
                
                const screenVideoTrack = this.screenShareStream.getVideoTracks()[0];
                if (videoSender) {
                    await videoSender.replaceTrack(screenVideoTrack);
                    console.log('✅ Screen share video track replaced in peer connection');
                } else {
                    console.warn('⚠️ No video sender found in peer connection - adding screen track and renegotiating');
                    this.peerConnection.addTrack(screenVideoTrack, this.screenShareStream);
                }
                
                // Also handle audio if available
                const audioSender = this.peerConnection.getSenders().find(sender => 
                    sender.track && sender.track.kind === 'audio'
                );
                const screenAudioTrack = this.screenShareStream.getAudioTracks()[0];
                
                if (audioSender && screenAudioTrack) {
                    // Note: We keep the microphone audio, don't replace it with screen audio
                    console.log('Screen audio available but keeping microphone audio');
                }

                // Renegotiate to propagate new encoding/parameters to remote peer
                try { await this.createAndSendOffer(); console.log('🔄 Sent renegotiation offer after starting screen share'); } catch (renoErr) { console.warn('Failed to renegotiate after starting screen share:', renoErr); }
            } else {
                console.warn('⚠️ No peer connection available for screen sharing');
            }
            
            // Update local video to show screen share
            const localVideo = document.getElementById('localVideo');
            if (localVideo) {
                localVideo.srcObject = this.screenShareStream;
                console.log('✅ Local video updated to show screen share');
            }
            
            // Also update waiting room video if still in waiting room
            const waitingRoomVideo = document.getElementById('waitingRoomVideo');
            if (waitingRoomVideo) {
                waitingRoomVideo.srcObject = this.screenShareStream;
                console.log('✅ Waiting room video updated to show screen share');
            }
            
            this.isScreenSharing = true;
            this.updateScreenShareButton();
            
            // Handle when user stops sharing via browser controls
            this.screenShareStream.getVideoTracks()[0].onended = () => {
                console.log('Screen share ended by user via browser controls');
                this.stopScreenShare();
            };
            
            // Notify other participants
            if (this.socket) {
                this.socket.emit('screen_share_start', {
                    session_id: this.sessionId
                });
                console.log('✅ Screen share start notification sent');
            }
            
            this.showNotification('Screen sharing started - students can now see your screen', 'success');
            
        } catch (error) {
            console.error('❌ Error starting screen share:', error);
            
            if (error.name === 'NotAllowedError') {
                this.showError('Screen sharing permission denied. Please allow screen sharing and try again.');
            } else if (error.name === 'NotSupportedError') {
                this.showError('Screen sharing is not supported in this browser.');
            } else {
                this.showError('Failed to start screen sharing. Please try again.');
            }
        }
    }
    
    async stopScreenShare() {
        try {
            console.log('🛑 Stopping screen share...');
            
            if (this.screenShareStream) {
                this.screenShareStream.getTracks().forEach(track => {
                    track.stop();
                    console.log(`Stopped ${track.kind} track`);
                });
                this.screenShareStream = null;
            }
            
            // Replace with camera stream (if available)
            if (this.peerConnection && this.localStream) {
                const videoSender = this.peerConnection.getSenders().find(sender => 
                    sender.track && sender.track.kind === 'video'
                );
                
                if (videoSender) {
                    const cameraTrack = this.localStream.getVideoTracks()[0];
                    if (cameraTrack) {
                        await videoSender.replaceTrack(cameraTrack);
                        console.log('✅ Replaced screen share with camera track');
                    } else {
                        // No camera available, send null track
                        await videoSender.replaceTrack(null);
                        console.log('✅ Replaced screen share with null (no camera)');
                    }
                }

                // Renegotiate to propagate change back to camera
                try { await this.createAndSendOffer(); console.log('🔄 Sent renegotiation offer after stopping screen share'); } catch (renoErr) { console.warn('Failed to renegotiate after stopping screen share:', renoErr); }
            }
            
            // Update local video to show camera (or hide if no camera)
            const localVideo = document.getElementById('localVideo');
            if (localVideo && this.localStream) {
                localVideo.srcObject = this.localStream;
                console.log('✅ Local video updated to show camera');
            }
            
            // Update waiting room video too
            const waitingRoomVideo = document.getElementById('waitingRoomVideo');
            if (waitingRoomVideo && this.localStream) {
                waitingRoomVideo.srcObject = this.localStream;
                console.log('✅ Waiting room video updated to show camera');
            }
            
            this.isScreenSharing = false;
            this.updateScreenShareButton();
            
            // Notify other participants
            if (this.socket) {
                this.socket.emit('screen_share_stop', {
                    session_id: this.sessionId
                });
                console.log('✅ Screen share stop notification sent');
            }
            
            this.showNotification('Screen sharing stopped', 'info');
            
        } catch (error) {
            console.error('❌ Error stopping screen share:', error);
            this.showError('Failed to stop screen sharing');
        }
    }
    
    // Recording methods removed
    
    saveNotes() {
        console.log('Saving session notes...');
        
        this.socket.emit('save_notes', {
            session_id: this.sessionId,
            notes: this.sessionNotes
        });
    }
    
    updateMediaButtons() {
        const audioBtn = document.getElementById('micToggle');
        if (audioBtn) {
            const icon = audioBtn.querySelector('i');
            if (icon) icon.className = this.isAudioEnabled ? 'fas fa-microphone' : 'fas fa-microphone-slash';
            audioBtn.classList.toggle('off', !this.isAudioEnabled);
        }
        const videoBtn = document.getElementById('camToggle');
        if (videoBtn) {
            const icon = videoBtn.querySelector('i');
            if (icon) icon.className = this.isVideoEnabled ? 'fas fa-video' : 'fas fa-video-slash';
            videoBtn.classList.toggle('off', !this.isVideoEnabled);
        }
    }
    
    updateWaitingRoomButtons() {
        const lobbyMic = document.getElementById('lobbyMicBtn');
        if (lobbyMic) {
            const icon = lobbyMic.querySelector('i');
            if (icon) icon.className = this.isAudioEnabled ? 'fas fa-microphone' : 'fas fa-microphone-slash';
            lobbyMic.classList.toggle('off', !this.isAudioEnabled);
        }
        const lobbyCam = document.getElementById('lobbyCamBtn');
        if (lobbyCam) {
            const icon = lobbyCam.querySelector('i');
            if (icon) icon.className = this.isVideoEnabled ? 'fas fa-video' : 'fas fa-video-slash';
            lobbyCam.classList.toggle('off', !this.isVideoEnabled);
        }
        const previewOff = document.getElementById('lobbyPreviewOff');
        if (previewOff) previewOff.classList.toggle('hidden', this.isVideoEnabled);
    }
    
    updateAllMediaButtons() {
        this.updateMediaButtons();
        this.updateWaitingRoomButtons();
    }
    
    updateVideoPlaceholder() {
        const previewOff = document.getElementById('lobbyPreviewOff');
        if (previewOff) previewOff.classList.toggle('hidden', this.isVideoEnabled);
        const localVideo = document.getElementById('localVideo');
        const pipPlaceholder = document.getElementById('localPipPlaceholder');
        if (localVideo) localVideo.style.display = this.isVideoEnabled ? '' : 'none';
        if (pipPlaceholder) pipPlaceholder.classList.toggle('hidden', this.isVideoEnabled);
    }
    
    updateScreenShareButton() {
        const btn = document.getElementById('screenShareBtn');
        if (btn) btn.classList.toggle('active', this.isScreenSharing);
    }
    
    updateRecordingButtons() { /* no-op: recording removed */ }
    
    showWaitingRoom() {
        const lobby = document.getElementById('vcLobby');
        const call = document.getElementById('vcCall');
        if (lobby) lobby.classList.remove('hidden');
        if (call) call.classList.remove('active');
        this.updateWaitingRoomMessage('Connecting to session...');
        this.updateWaitingRoomButtons();
        this.updateVideoPlaceholder();
        this.attachStreamToWaitingRoom();
    }
    
    attachStreamToWaitingRoom() {
        if (this.localStream) {
            const preview = document.getElementById('lobbyPreview');
            if (preview) {
                preview.srcObject = this.localStream;
                preview.muted = true;
                preview.onloadedmetadata = () => preview.play().catch(()=>{});
                if (preview.readyState >= 2) preview.play().catch(()=>{});
            }
            const previewOff = document.getElementById('lobbyPreviewOff');
            if (previewOff) previewOff.classList.toggle('hidden', this.isVideoEnabled);
        }
    }
    
    updateWaitingRoomMessage(message) {
        const el = document.getElementById('lobbyStatus');
        if (el) { const span = el.querySelector('span'); if (span) span.textContent = message; }
    }
    
    showStartCallButton() {
        const btn = document.getElementById('joinCallBtn');
        if (btn) btn.classList.add('visible');
        this.updateWaitingRoomMessage('Both ready. Click to start the call.');
    }
    
    updateConnectionStatus(status, type = 'info') {
        if (this.isInCall) this.vcToast(status, type);
    }
    
    // Harmonize connection indicators with student client
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

    // Update counselor/student presence dots in waiting room
    updateParticipantIndicators(counselorPresent = true, studentPresent = false) {
        // Counselor indicator
        const counselorIndicator = document.getElementById('counselorIndicator');
        const counselorStatus = counselorIndicator?.parentElement?.nextElementSibling;
        if (counselorIndicator) {
            counselorIndicator.className = counselorPresent ?
                'w-4 h-4 rounded-full bg-emerald-500' :
                'w-4 h-4 rounded-full bg-slate-300';
            const pingDiv = counselorIndicator.nextElementSibling;
            if (pingDiv) {
                pingDiv.className = counselorPresent ?
                    'absolute inset-0 rounded-full bg-emerald-500 animate-ping opacity-75' :
                    'absolute inset-0 rounded-full bg-slate-300 animate-ping opacity-75';
            }
        }
        if (counselorStatus) {
            counselorStatus.textContent = counselorPresent ? 'You (Ready)' : 'You';
            counselorStatus.className = counselorPresent ?
                'text-sm font-medium text-emerald-600' :
                'text-sm font-medium text-slate-600';
        }

        // Student indicator
        const studentIndicator = document.getElementById('studentIndicator');
        const studentStatus = studentIndicator?.parentElement?.nextElementSibling;
        if (studentIndicator) {
            studentIndicator.className = studentPresent ?
                'w-4 h-4 rounded-full bg-emerald-500' :
                'w-4 h-4 rounded-full bg-slate-300';
            const pingDiv = studentIndicator.nextElementSibling;
            if (pingDiv) {
                pingDiv.className = studentPresent ?
                    'absolute inset-0 rounded-full bg-emerald-500 animate-ping opacity-75' :
                    'absolute inset-0 rounded-full bg-slate-300 animate-ping opacity-75';
            }
        }
        if (studentStatus) {
            studentStatus.textContent = studentPresent ? 'Student (Ready)' : 'Student';
            studentStatus.className = studentPresent ?
                'text-sm font-medium text-emerald-600' :
                'text-sm font-medium text-slate-600';
        }
    }

    updateConnectionQuality(quality) {
        this.connectionQuality = quality;
        // Update UI label
        const qualityElement = document.getElementById('connectionQuality');
        if (qualityElement) {
            const label = quality.charAt(0).toUpperCase() + quality.slice(1);
            qualityElement.textContent = label;
            // lightweight class mapping
            if (/excellent/i.test(quality)) qualityElement.className = 'text-xs font-medium text-emerald-800';
            else if (/good/i.test(quality)) qualityElement.className = 'text-xs font-medium text-yellow-800';
            else if (/poor/i.test(quality)) qualityElement.className = 'text-xs font-medium text-red-800';
            else qualityElement.className = 'text-xs font-medium text-blue-800';
        }
        // Adapt outbound bitrate
        this.applyAdaptiveBitrate?.(quality);
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
                    // Prefer a clean rebuild to clear any stuck transceivers/states
                    await this.rebuildPeerConnection('auto_recovery');
                    // Ask peer to renegotiate
                    this.socket?.emit('reconnect_request', { session_id: this.sessionId });
                }
            } catch (e) {
                console.warn('Office recovery attempt failed:', e);
            }
        }, delay);
    }

    drainPendingIceCandidates() {
        if (!this.peerConnection || !this.peerConnection.remoteDescription) return;
        const queue = this.pendingIceCandidates || [];
        this.pendingIceCandidates = [];
        queue.forEach(async (c) => {
            try { await this.peerConnection.addIceCandidate(c); } catch (e) {
                console.debug('Failed to add queued ICE candidate:', e?.name || e);
            }
        });
    }

    async rebuildPeerConnection(reason = 'manual') {
        console.log('Rebuilding RTCPeerConnection (office) due to:', reason);
        try {
            this.reconnectInProgress = true;
            const oldPc = this.peerConnection;
            if (oldPc) {
                try { oldPc.ontrack = null; oldPc.onicecandidate = null; oldPc.onconnectionstatechange = null; oldPc.oniceconnectionstatechange = null; } catch (_) {}
                try { oldPc.close(); } catch (_) {}
            }
            this.peerConnection = null;
            await this.createPeerConnection();
            // Re-add local tracks if available
            if (this.localStream) {
                this.localStream.getTracks().forEach(t => {
                    try { this.peerConnection.addTrack(t, this.localStream); } catch (_) {}
                });
            }
            this.ensureReceiveTransceivers();
            // As polite peer, create an offer to re-sync
            try { await this.createAndSendOffer(); } catch (_) {}
        } catch (e) {
            console.warn('Failed to rebuild peer connection (office):', e);
        } finally {
            setTimeout(() => { this.reconnectInProgress = false; }, 1500);
        }
    }

    // Lightweight quality monitor using getStats
    monitorConnectionQuality() {
        try { if (this._qualityTimer) { clearInterval(this._qualityTimer); this._qualityTimer = null; } } catch (_) {}
        this._qualityTimer = setInterval(async () => {
            try {
                if (!this.peerConnection) return;
                const stats = await this.peerConnection.getStats(null);
                let inboundAudio, inboundVideo;
                stats.forEach(report => {
                    if (report.type === 'inbound-rtp' && !report.isRemote) {
                        if (report.kind === 'audio') inboundAudio = report;
                        if (report.kind === 'video') inboundVideo = report;
                    }
                });
                const target = inboundVideo || inboundAudio;
                if (!target) return;
                const quality = this.calculateConnectionQuality({
                    packetsLost: target.packetsLost || 0,
                    packetsReceived: target.packetsReceived || 0,
                    jitter: target.jitter || 0
                });
                this.updateConnectionQuality(quality);
            } catch (_) { /* ignore */ }
        }, 5000);
    }

    calculateConnectionQuality(stats) {
        const packetsLost = stats.packetsLost || 0;
        const packetsReceived = stats.packetsReceived || 0;
        const total = packetsLost + packetsReceived;
        const lossRate = total > 0 ? (packetsLost / total) : 0;
        const jitter = stats.jitter || 0;
        if (lossRate < 0.02 && jitter < 0.03) return 'excellent';
        if (lossRate < 0.05 && jitter < 0.08) return 'good';
        return 'poor';
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
        if (modal) modal.classList.add('active');
    }
    
    hideEndSessionModal() {
        const modal = document.getElementById('endSessionModal');
        if (modal) modal.classList.remove('active');
    }
    
    endSession() {
        console.log('Ending session...');
        this.socket.emit('end_session', { session_id: this.sessionId });
        this.cleanup();
        this.hideEndSessionModal();
        const cfg = window.VIDEO_SESSION_CONFIG || {};
        const url = cfg.endSessionUrl || `/office/session-completed/${this.sessionId}`;
        setTimeout(() => { window.location.href = url; }, 2000);
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
            window.location.href = `/office/session-completed/${this.sessionId}`;
        }, 3000);
    }
    // Timer helpers based on sessionStartAt provided by server
    startSessionTimer() {
        if (!this.sessionStartAt) return;
        if (this.sessionTimer) { clearInterval(this.sessionTimer); this.sessionTimer = null; }
        const update = () => {
            if (!this.sessionStartAt) return;
            const elapsedSec = Math.max(0, Math.floor((Date.now() - this.sessionStartAt.getTime()) / 1000));
            const hours = Math.floor(elapsedSec / 3600);
            const minutes = Math.floor((elapsedSec % 3600) / 60);
            const seconds = elapsedSec % 60;
            const timerEl = document.getElementById('vcTimerText');
            if (timerEl) {
                timerEl.textContent = hours > 0
                    ? `${String(hours).padStart(2,'0')}:${String(minutes).padStart(2,'0')}:${String(seconds).padStart(2,'0')}`
                    : `${String(minutes).padStart(2,'0')}:${String(seconds).padStart(2,'0')}`;
            }
        };
        update();
        this.sessionTimer = setInterval(update, 1000);
    }

    ensureSessionTimerRunning() {
        if (this.sessionStartAt && !this.sessionTimer) this.startSessionTimer();
    }

    stopSessionTimer() {
        if (this.sessionTimer) { clearInterval(this.sessionTimer); this.sessionTimer = null; }
    }

    // Recording removed: keep stubs to avoid errors if referenced
    async startRecording() { /* no-op: recording feature removed */ }
    async stopRecording() { /* no-op: recording feature removed */ }
    async uploadRecording(blob) { /* no-op: recording feature removed */ }
    
    cleanup() {
        console.log('Cleaning up video counseling session...');
        
        this.stopSessionTimer();
        this.stopHeartbeat();
        // Stop quality monitor
        if (this._qualityTimer) {
            try { clearInterval(this._qualityTimer); } catch (_) {}
            this._qualityTimer = null;
        }
        
        // Stop screen sharing if active
        if (this.isScreenSharing) {
            this.stopScreenShare();
        }
        
        // Stop recording if active
        if (this.isRecording) {
            this.stopRecording();
        }
        
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
        
        if (this.screenShareStream) {
            this.screenShareStream.getTracks().forEach(track => track.stop());
            this.screenShareStream = null;
        }
        
    // Do not force socket disconnect to allow reconnection
    this.isInCall = false;
        this.isConnected = false;
    this.persistLocalState();
    }
    
    showNotification(message, type = 'info') {
        this.vcToast(message, type);
    }
    
    showError(message) {
        console.error('Error:', message);
        this.vcToast(message, 'error');
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

    async onSocketReconnected() {
        try {
            this.updateConnectionStatus('Reconnected. Restoring session…', 'info');
            this.joinSession();
            if (this.wasInCallBeforeDisconnect || this.isInCall) {
                if (!this.localStream) {
                    await this.initializeMedia();
                }
                if (!this.peerConnection) {
                    await this.createPeerConnection();
                }
                this.socket.emit('reconnect_request', { session_id: this.sessionId });
                this.socket.emit('join_call', { session_id: this.sessionId });
            }
        } catch (e) {
            console.warn('Failed to restore session on reconnect:', e);
        }
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
        
        // Show selected tab content - specifically target .tab-content elements
        const selectedContent = document.querySelector(`.tab-content[data-tab="${tabName}"]`);
        if (selectedContent) {
            selectedContent.classList.remove('hidden');
            selectedContent.classList.add('active');
            console.log('Tab content shown for:', tabName);
        } else {
            console.error('Tab content not found for:', tabName);
        }
        
        // Add active class to selected button
        const selectedButton = document.querySelector(`.tab-button[data-tab="${tabName}"]`);
        if (selectedButton) {
            selectedButton.classList.add('active');
            console.log('Tab button activated for:', tabName);
        } else {
            console.error('Tab button not found for:', tabName);
        }
    }
    
    toggleFullScreen() {
        const container = document.getElementById('vcContainer');
        if (!container) return;
        if (document.fullscreenElement) {
            document.exitFullscreen().catch(()=>{});
        } else {
            container.requestFullscreen().catch(()=>{});
        }
        const btn = document.getElementById('fullscreenBtn');
        if (btn) {
            const icon = btn.querySelector('i');
            if (icon) icon.className = document.fullscreenElement ? 'fas fa-expand' : 'fas fa-compress';
        }
    }
    
    // Legacy stubs — auto-hide is now handled by initControlsAutoHide
    enterFullscreenMode() {}
    exitFullscreenMode() {}
    requestFullscreenOnCallStart() {}
    startControlsAutoHide() {}
    stopControlsAutoHide() {}
    showFullscreenInfo() {}
    hideFullscreenInfo() {}
    
    async changeCamera(deviceId) {
        if (!deviceId || !this.localStream) {
            console.warn('Cannot change camera - invalid device ID or no local stream');
            return;
        }
        
        try {
            console.log('Changing camera to device:', deviceId);
            
            // Stop current video track
            const videoTrack = this.localStream.getVideoTracks()[0];
            if (videoTrack) {
                videoTrack.stop();
            }
            
            // Get new video stream with selected device
            const newVideoStream = await navigator.mediaDevices.getUserMedia({
                video: {
                    deviceId: { exact: deviceId },
                    width: { ideal: 1920 },
                    height: { ideal: 1080 },
                    frameRate: { ideal: 30, max: 30 }
                },
                audio: false
            });
            
            // Replace video track in the stream
            const newVideoTrack = newVideoStream.getVideoTracks()[0];
            if (newVideoTrack) {
                // Remove old video track
                this.localStream.getVideoTracks().forEach(track => {
                    this.localStream.removeTrack(track);
                });
                
                // Add new video track
                this.localStream.addTrack(newVideoTrack);
                
                // Update video elements
                const localVideo = document.getElementById('localVideo');
                if (localVideo) {
                    localVideo.srcObject = this.localStream;
                }
                
                const waitingRoomVideo = document.getElementById('waitingRoomVideo');
                if (waitingRoomVideo) {
                    waitingRoomVideo.srcObject = this.localStream;
                }
                
                // Update peer connection if active
                if (this.peerConnection) {
                    const sender = this.peerConnection.getSenders().find(s => 
                        s.track && s.track.kind === 'video'
                    );
                    if (sender) {
                        await sender.replaceTrack(newVideoTrack);
                        try { await this.applyHighQualitySenderParams(); } catch (_) {}
                    }
                }
                
                // Ensure video state is maintained
                newVideoTrack.enabled = this.isVideoEnabled;
                this.updateVideoPlaceholder();
                
                this.showNotification('Camera changed successfully', 'success');
            }
            
        } catch (error) {
            console.error('Failed to change camera:', error);
            this.showNotification('Failed to change camera', 'error');
        }
    }
    
    async changeMicrophone(deviceId) {
        if (!deviceId || !this.localStream) return;
        
        try {
            console.log('Changing microphone to device:', deviceId);
            
            // Stop current audio track
            const audioTrack = this.localStream.getAudioTracks()[0];
            if (audioTrack) {
                audioTrack.stop();
            }
            
            // Get new audio stream with selected device
            const newAudioStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    deviceId: { exact: deviceId },
                    ...this.mediaConstraints.audio
                },
                video: false
            });
            
            // Replace audio track in the stream
            const newAudioTrack = newAudioStream.getAudioTracks()[0];
            if (newAudioTrack) {
                // Remove old audio track
                this.localStream.getAudioTracks().forEach(track => {
                    this.localStream.removeTrack(track);
                });
                
                // Add new audio track
                this.localStream.addTrack(newAudioTrack);
                
                // Update peer connection if active
                if (this.peerConnection) {
                    const sender = this.peerConnection.getSenders().find(s => 
                        s.track && s.track.kind === 'audio'
                    );
                    if (sender) {
                        await sender.replaceTrack(newAudioTrack);
                    }
                }
                
                // Ensure audio state is maintained
                newAudioTrack.enabled = this.isAudioEnabled;
                
                this.showNotification('Microphone changed successfully', 'success');
            }
            
        } catch (error) {
            console.error('Failed to change microphone:', error);
            this.showNotification('Failed to change microphone', 'error');
        }
    }

    // Remote peer media toggle handlers (student -> office)
    handleRemoteAudioToggle(data) {
        try {
            const name = data?.name || 'Student';
            const on = !!data?.audio_enabled;
            console.log(`${name} ${on ? 'enabled' : 'disabled'} their microphone`);
            // Optional: surface a subtle notification. UI has no dedicated icon now.
            // this.showNotification(`${name} ${on ? 'unmuted' : 'muted'} their mic`, on ? 'info' : 'warning');
        } catch (_) {}
    }

    handleRemoteVideoToggle(data) {
        try {
            const on = !!data?.video_enabled;
            const remoteVideo = document.getElementById('remoteVideo');
            const remotePlaceholder = document.getElementById('remoteVideoPlaceholder');
            if (!remoteVideo || !remotePlaceholder) return;
            if (on) {
                // Re-attach stream if needed and ensure playback
                if (this.remoteStream && remoteVideo.srcObject !== this.remoteStream) {
                    try { remoteVideo.srcObject = this.remoteStream; } catch (_) {}
                }
                try { remoteVideo.autoplay = true; remoteVideo.playsInline = true; } catch (_) {}
                remoteVideo.classList.remove('hidden');
                remotePlaceholder.classList.add('hidden');
                const tryPlay = () => {
                    remoteVideo.play().catch(e => {
                        console.warn('Remote video play (toggle on) blocked:', e?.name || e);
                        if (!remoteVideo.muted) {
                            remoteVideo.muted = true;
                            remoteVideo.play().catch(() => {});
                            this._awaitFirstUserGestureToUnmute(remoteVideo);
                        }
                    });
                };
                if (remoteVideo.readyState >= 2) tryPlay();
                remoteVideo.onloadedmetadata = () => tryPlay();
            } else {
                remoteVideo.classList.add('hidden');
                remotePlaceholder.classList.remove('hidden');
            }
        } catch (e) {
            console.warn('Failed to handle remote video toggle:', e?.name || e);
        }
    }

    // Method to force show tabs (for debugging)
    forceShowTabs() {
        console.log('=== FORCE SHOWING TABS ===');
        
        // Make sure the side panel is visible
        const sidePanel = document.querySelector('.w-96');
        if (sidePanel) {
            sidePanel.style.display = 'flex';
            console.log('Side panel made visible');
        }
        
        // Show all tab contents temporarily for debugging
        const tabContents = document.querySelectorAll('.tab-content');
        tabContents.forEach((content, index) => {
            if (index === 0) {
                content.classList.remove('hidden');
                content.classList.add('active');
                content.style.display = 'block';
            }
        });
        
        const firstButton = document.querySelector('.tab-button');
        if (firstButton) firstButton.classList.add('active');
    }

    // ═══ CHAT SYSTEM ═══
    initChat() {
        this.chatOpen = false;
        this.unreadCount = 0;
        this._typingTimeout = null;
        if (this.socket) {
            this.socket.on('session_chat_message', (data) => this.receiveChatMessage(data));
            this.socket.on('session_chat_typing', (data) => this.handleRemoteTyping(data));
        }
        const sendBtn = document.getElementById('chatSendBtn');
        const input = document.getElementById('chatInput');
        const closeBtn = document.getElementById('chatCloseBtn');
        const toggleBtn = document.getElementById('chatToggle');
        if (sendBtn) sendBtn.addEventListener('click', () => this.sendChatMessage());
        if (input) {
            input.addEventListener('keydown', (e) => { if (e.key === 'Enter') this.sendChatMessage(); });
            input.addEventListener('input', () => this.emitTyping());
        }
        if (closeBtn) closeBtn.addEventListener('click', () => this.toggleChatPanel(false));
        if (toggleBtn) toggleBtn.addEventListener('click', () => this.toggleChatPanel());
    }
    toggleChatPanel(forceState) {
        const panel = document.getElementById('vcChat');
        const area = document.getElementById('vcVideoArea');
        if (!panel) return;
        this.chatOpen = forceState !== undefined ? forceState : !this.chatOpen;
        panel.classList.toggle('open', this.chatOpen);
        if (area) area.classList.toggle('chat-open', this.chatOpen);
        if (this.chatOpen) { this.unreadCount = 0; this.updateChatBadge(); }
        const toggleBtn = document.getElementById('chatToggle');
        if (toggleBtn) toggleBtn.classList.toggle('active', this.chatOpen);
    }
    sendChatMessage() {
        const input = document.getElementById('chatInput');
        if (!input) return;
        const text = input.value.trim();
        if (!text || !this.socket) return;
        this.socket.emit('session_chat_message', { session_id: this.sessionId, message: text });
        input.value = '';
    }
    receiveChatMessage(data) {
        const container = document.getElementById('chatMessages');
        if (!container) return;
        const isSelf = data.user_id === this.userId;
        const div = document.createElement('div');
        div.className = 'vc-msg ' + (isSelf ? 'sent' : 'received');
        const time = new Date(data.timestamp).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});
        div.innerHTML = (!isSelf ? `<div class="vc-msg-name">${this._esc(data.name)}</div>` : '') +
            `<div>${this._esc(data.message)}</div><div class="vc-msg-time">${time}</div>`;
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
        if (!isSelf && !this.chatOpen) { this.unreadCount++; this.updateChatBadge(); this.playChatSound(); }
    }
    updateChatBadge() {
        const badge = document.getElementById('chatBadge');
        if (!badge) return;
        if (this.unreadCount > 0) { badge.textContent = this.unreadCount; badge.classList.remove('hidden'); }
        else { badge.classList.add('hidden'); }
    }
    emitTyping() {
        if (this._typingTimeout) clearTimeout(this._typingTimeout);
        if (this.socket) this.socket.emit('session_chat_typing', { session_id: this.sessionId, is_typing: true });
        this._typingTimeout = setTimeout(() => {
            if (this.socket) this.socket.emit('session_chat_typing', { session_id: this.sessionId, is_typing: false });
        }, 2000);
    }
    handleRemoteTyping(data) {
        const el = document.getElementById('chatTyping');
        if (!el) return;
        el.textContent = data.is_typing ? `${data.name} is typing…` : '';
    }
    playChatSound() {
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator(); const gain = ctx.createGain();
            osc.connect(gain); gain.connect(ctx.destination);
            osc.frequency.value = 800; gain.gain.value = 0.1;
            osc.start(); osc.stop(ctx.currentTime + 0.15);
        } catch(_){}
    }
    _esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

    // ═══ NOTES PANEL ═══
    initNotes() {
        const toggleBtn = document.getElementById('notesToggle');
        const closeBtn = document.getElementById('notesCloseBtn');
        const saveBtn = document.getElementById('notesSaveBtn');
        if (toggleBtn) toggleBtn.addEventListener('click', () => this.toggleNotesPanel());
        if (closeBtn) closeBtn.addEventListener('click', () => this.toggleNotesPanel(false));
        if (saveBtn) saveBtn.addEventListener('click', () => this.saveNotes());
        // Auto-save on typing
        const textarea = document.getElementById('notesTextarea');
        if (textarea) {
            textarea.addEventListener('input', () => {
                clearTimeout(this._notesAutoSave);
                this._notesAutoSave = setTimeout(() => this.saveNotes(), 3000);
            });
        }
    }
    toggleNotesPanel(forceState) {
        const panel = document.getElementById('vcNotes');
        if (!panel) return;
        const open = forceState !== undefined ? forceState : !panel.classList.contains('open');
        panel.classList.toggle('open', open);
        const btn = document.getElementById('notesToggle');
        if (btn) btn.classList.toggle('active', open);
    }
    saveNotes() {
        const textarea = document.getElementById('notesTextarea');
        const status = document.getElementById('notesStatus');
        if (!textarea) return;
        const cfg = window.VIDEO_SESSION_CONFIG || {};
        const csrfToken = cfg.csrfToken || document.querySelector('meta[name="csrf-token"]')?.content || '';
        fetch(cfg.endSessionApiUrl || `/office/api/session/${this.sessionId}/notes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify({ notes: textarea.value })
        }).then(r => {
            if (status) { status.textContent = 'Saved'; setTimeout(() => status.textContent = '', 2000); }
        }).catch(() => {
            if (status) { status.textContent = 'Save failed'; }
        });
    }

    // ═══ TOAST NOTIFICATIONS ═══
    vcToast(message, type = 'info') {
        const zone = document.getElementById('vcToastZone');
        if (!zone) return;
        const iconMap = { info:'fa-info-circle', success:'fa-check-circle', warning:'fa-exclamation-triangle', error:'fa-times-circle' };
        const t = document.createElement('div');
        t.className = 'vc-toast';
        t.innerHTML = `<i class="fas ${iconMap[type]||iconMap.info} vc-toast-icon ${type}"></i><span>${this._esc(message)}</span>`;
        zone.appendChild(t);
        setTimeout(() => { t.classList.add('fade-out'); setTimeout(() => t.remove(), 300); }, 4000);
    }

    // ═══ RECONNECTION OVERLAY ═══
    showReconnectOverlay(msg) { const el = document.getElementById('vcReconnect'); if (el) el.classList.add('active'); }
    hideReconnectOverlay() { const el = document.getElementById('vcReconnect'); if (el) el.classList.remove('active'); }

    // ═══ CONTROLS AUTO-HIDE ═══
    initControlsAutoHide() {
        const controls = document.getElementById('vcControls');
        const container = document.getElementById('vcCall');
        if (!controls || !container) return;
        let hideTimer, overControls = false;
        const show = () => { controls.classList.remove('auto-hidden'); clearTimeout(hideTimer); if (!overControls) hideTimer = setTimeout(hide, 3000); };
        const hide = () => { if (!overControls) controls.classList.add('auto-hidden'); };
        container.addEventListener('mousemove', show);
        container.addEventListener('touchstart', show, {passive:true});
        controls.addEventListener('mouseenter', () => { overControls = true; clearTimeout(hideTimer); });
        controls.addEventListener('mouseleave', () => { overControls = false; hideTimer = setTimeout(hide, 1500); });
        hideTimer = setTimeout(hide, 3000);
    }

    // ═══ PIP DRAG ═══
    initPipDrag() {
        const pip = document.getElementById('vcLocalPip');
        if (!pip) return;
        let dragging = false, ox, oy;
        pip.addEventListener('mousedown', (e) => { dragging = true; ox = e.offsetX; oy = e.offsetY; pip.style.cursor = 'grabbing'; });
        document.addEventListener('mousemove', (e) => { if (!dragging) return; pip.style.left = (e.clientX - ox) + 'px'; pip.style.top = (e.clientY - oy) + 'px'; pip.style.right = 'auto'; pip.style.bottom = 'auto'; });
        document.addEventListener('mouseup', () => { dragging = false; pip.style.cursor = 'grab'; });
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    const cfg = window.VIDEO_SESSION_CONFIG;
    const sessionData = cfg || window.sessionData || {};
    const sid = sessionData.sessionId;
    const uid = sessionData.userId;
    const uname = sessionData.userName || '';

    if (sid && uid) {
        console.log('Initializing video counseling (office) for session:', sid);
        window.videoCounselingClient = new VideoCounselingClientOffice(sid, uid, uname);
    } else {
        console.error('Missing session data for video counseling');
    }
});

window.addEventListener('beforeunload', function() {
    if (window.videoCounselingClient) window.videoCounselingClient.cleanup();
});

document.addEventListener('visibilitychange', function() {
    // stub for future quality adaptation
});