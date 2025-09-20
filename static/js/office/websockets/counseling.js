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
        this.isRecording = false;
        this.isConnected = false;
        this.sessionTimer = null;
        this.startTime = null;
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
                console.warn('[VideoCounseling][Office] No TURN servers configured. Cross-ISP / mobile calls may show black video. Configure TURN_HOST or ICE_SERVERS_JSON.');
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
            console.log('🚀 Initializing Video Counseling Client for Office...');
            this.updateConnectionStatus('Initializing...', 'info');
            this.restoreLocalState();
            this.initializeSocket();
            this.setupEventListeners();
            this.installNavigationGuards();
            
            // Request media access BEFORE showing waiting room
            await this.initializeMedia();
            
            // Device list will be populated AFTER successful media access
            await this.populateDeviceList();
            
            // NOW show waiting room with media already available
            this.showWaitingRoom();
            
            // Initialize participant indicators - counselor is connected, student is not yet
            this.updateParticipantIndicators(true, false);
        } catch (error) {
            console.error('❌ Failed to initialize video counseling:', error);
            this.updateConnectionStatus('Initialization failed', 'error');
            this.showError('Failed to initialize video calling. Please check camera/microphone permissions and refresh the page.');
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
        
        this.socket.on('session_joined', (data) => {
            console.log('Successfully joined session:', data);
            this.updateWaitingRoomMessage('Waiting for student to join...');
            
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
                this.updateConnectionStatus('Student disconnected', 'error');
                this.updateParticipantIndicators(true, false);
                this.handleStudentDisconnect();
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
        // Media control buttons (main call interface)
        const toggleAudioBtn = document.getElementById('micToggle');
        if (toggleAudioBtn) {
            toggleAudioBtn.addEventListener('click', () => this.toggleAudio());
        }
        
        const toggleVideoBtn = document.getElementById('cameraToggle');
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
        
        // Screen sharing
        const screenShareBtn = document.getElementById('screenShareToggle');
        if (screenShareBtn) {
            screenShareBtn.addEventListener('click', () => this.toggleScreenShare());
        }
        
        // Recording controls
        const recordingBtn = document.getElementById('recordButton');
        if (recordingBtn) {
            recordingBtn.addEventListener('click', () => {
                if (this.isRecording) {
                    this.stopRecording();
                } else {
                    this.startRecording();
                }
            });
        }
        
        // End call button
        const endCallBtn = document.getElementById('endSessionButton');
        if (endCallBtn) {
            endCallBtn.addEventListener('click', () => this.showEndSessionModal());
        }
        
        // Start call button
        const startCallBtn = document.getElementById('startCallBtn');
        if (startCallBtn) {
            startCallBtn.addEventListener('click', () => {
                // User gesture — best time to request fullscreen
                this.startCall();
                this.requestFullscreenOnCallStart();
            });
        }
        
        // Fullscreen button
        const fullscreenBtn = document.getElementById('fullScreenToggle');
        if (fullscreenBtn) {
            fullscreenBtn.addEventListener('click', () => this.toggleFullScreen());
        }
        
        // Device selection
        const cameraSelect = document.getElementById('cameraSelect');
        if (cameraSelect) {
            cameraSelect.addEventListener('change', (e) => {
                const deviceId = e.target.value;
                if (deviceId && this.localStream) {
                    this.changeCamera(deviceId);
                } else {
                    console.warn('Cannot change camera: no device selected or no media stream');
                }
            });
        }
        
        const micSelect = document.getElementById('microphoneSelect');
        if (micSelect) {
            micSelect.addEventListener('change', (e) => {
                const deviceId = e.target.value;
                if (deviceId && this.localStream) {
                    this.changeMicrophone(deviceId);
                } else {
                    console.warn('Cannot change microphone: no device selected or no media stream');
                }
            });
        }
        
        // Tab switching
        const tabButtons = document.querySelectorAll('.tab-button');
        tabButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                // Find the button element (in case user clicks on child elements like icon or span)
                const buttonElement = e.currentTarget;
                const tabName = buttonElement.dataset.tab;
                if (tabName) {
                    console.log('Tab button clicked:', tabName);
                    this.switchTab(tabName);
                } else {
                    console.error('No tab name found on button:', buttonElement);
                }
            });
        });
        
        // Notes functionality
        const notesTextarea = document.getElementById('sessionNotes');
        if (notesTextarea) {
            notesTextarea.addEventListener('input', (e) => {
                this.sessionNotes = e.target.value;
            });
        }
        
        const saveNotesBtn = document.getElementById('saveNotes');
        if (saveNotesBtn) {
            saveNotesBtn.addEventListener('click', () => this.saveNotes());
        }
        
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
        console.log('=== COUNSELOR STARTING VIDEO CALL ===');
        console.log('Session ID:', this.sessionId);
        console.log('Is in call before:', this.isInCall);
        
        try {
            await this.createPeerConnection();
            console.log('Peer connection created successfully');
            
            // Don't show call UI immediately - wait for connection to establish
            this.startSessionTimer();
            this.isInCall = true;
            console.log('Is in call after:', this.isInCall);

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
        console.log('=== SHOWING CALL UI ===');
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
            } else {
                console.error('First tab button has no data-tab attribute');
            }
        } else {
            console.error('No tab buttons found');
        }
        
        // Debug: log all available tabs
        const allTabs = document.querySelectorAll('.tab-button');
        const allContents = document.querySelectorAll('.tab-content');
        console.log('Available tab buttons:', allTabs.length);
        console.log('Available tab contents:', allContents.length);
        
        allTabs.forEach((tab, index) => {
            console.log(`Tab ${index}:`, tab.getAttribute('data-tab'), tab);
        });
        
        allContents.forEach((content, index) => {
            console.log(`Content ${index}:`, content.getAttribute('data-tab'), content);
        });
        
        // Initialize tabs properly
        this.initializeTabs();
        
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
        
        // Update all media button states when showing call UI
        this.updateAllMediaButtons();
        this.updateVideoPlaceholder();
        // Try entering fullscreen automatically when the call UI becomes visible
        this.requestFullscreenOnCallStart();
        
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
    
    startRecording() {
        console.log('Starting session recording...');
        
        this.socket.emit('start_recording', {
            session_id: this.sessionId
        });
        
        this.isRecording = true;
        this.updateRecordingButtons();
        this.showNotification('Recording started', 'success');
    }
    
    stopRecording() {
        console.log('Stopping session recording...');
        
        this.socket.emit('stop_recording', {
            session_id: this.sessionId
        });
        
        this.isRecording = false;
        this.updateRecordingButtons();
        this.showNotification('Recording stopped', 'info');
    }
    
    saveNotes() {
        console.log('Saving session notes...');
        
        this.socket.emit('save_notes', {
            session_id: this.sessionId,
            notes: this.sessionNotes
        });
    }
    
    updateMediaButtons() {
        // Update main call interface buttons
        const audioBtn = document.getElementById('micToggle');
        const videoBtn = document.getElementById('cameraToggle');
        
        if (audioBtn) {
            const icon = audioBtn.querySelector('i');
            if (icon) {
                icon.className = this.isAudioEnabled ? 'fas fa-microphone' : 'fas fa-microphone-slash';
            }
            audioBtn.className = this.isAudioEnabled ? 
                'w-12 h-12 bg-green-500 hover:bg-green-600 rounded-full flex items-center justify-center transition-all duration-300 hover:scale-110' : 
                'w-12 h-12 bg-red-500 hover:bg-red-600 rounded-full flex items-center justify-center transition-all duration-300 hover:scale-110';
            
            // Update title attribute for accessibility
            audioBtn.title = this.isAudioEnabled ? 'Mute microphone' : 'Unmute microphone';
        }
        
        if (videoBtn) {
            const icon = videoBtn.querySelector('i');
            if (icon) {
                icon.className = this.isVideoEnabled ? 'fas fa-video' : 'fas fa-video-slash';
            }
            videoBtn.className = this.isVideoEnabled ? 
                'w-12 h-12 bg-green-500 hover:bg-green-600 rounded-full flex items-center justify-center transition-all duration-300 hover:scale-110' : 
                'w-12 h-12 bg-red-500 hover:bg-red-600 rounded-full flex items-center justify-center transition-all duration-300 hover:scale-110';
            
            // Update title attribute for accessibility
            videoBtn.title = this.isVideoEnabled ? 'Turn off camera' : 'Turn on camera';
        }
    }
    
    updateWaitingRoomButtons() {
        // Update waiting room buttons
        const waitingRoomMicToggle = document.getElementById('waitingRoomMicToggle');
        const waitingRoomCameraToggle = document.getElementById('waitingRoomCameraToggle');
        
        console.log('Updating waiting room buttons - audio:', this.isAudioEnabled, 'video:', this.isVideoEnabled);
        
        if (waitingRoomMicToggle) {
            const icon = waitingRoomMicToggle.querySelector('i');
            if (icon) {
                icon.className = this.isAudioEnabled ? 'fas fa-microphone text-green-600 group-hover:scale-110 transition-transform duration-300' : 'fas fa-microphone-slash text-red-600 group-hover:scale-110 transition-transform duration-300';
            }
            
            // Update button styling based on state - use the original template classes
            const baseClasses = 'w-12 h-12 rounded-full shadow-lg hover:shadow-xl flex items-center justify-center border border-slate-200 transition-all duration-300 hover:scale-110 group';
            waitingRoomMicToggle.className = baseClasses + (this.isAudioEnabled ? ' bg-white' : ' bg-red-50');
            
            // Update title attribute
            waitingRoomMicToggle.title = this.isAudioEnabled ? 'Mute microphone' : 'Unmute microphone';
        } else {
            console.warn('Waiting room mic toggle button not found');
        }
        
        if (waitingRoomCameraToggle) {
            const icon = waitingRoomCameraToggle.querySelector('i');
            if (icon) {
                icon.className = this.isVideoEnabled ? 'fas fa-video text-green-600 group-hover:scale-110 transition-transform duration-300' : 'fas fa-video-slash text-red-600 group-hover:scale-110 transition-transform duration-300';
            }
            
            // Update button styling based on state - use the original template classes
            const baseClasses = 'w-12 h-12 rounded-full shadow-lg hover:shadow-xl flex items-center justify-center border border-slate-200 transition-all duration-300 hover:scale-110 group';
            waitingRoomCameraToggle.className = baseClasses + (this.isVideoEnabled ? ' bg-white' : ' bg-red-50');
            
            // Update title attribute
            waitingRoomCameraToggle.title = this.isVideoEnabled ? 'Turn off camera' : 'Turn on camera';
        } else {
            console.warn('Waiting room camera toggle button not found');
        }
    }
    
    updateAllMediaButtons() {
        // Update both waiting room and call interface buttons
        this.updateMediaButtons();
        this.updateWaitingRoomButtons();
    }
    
    updateVideoPlaceholder() {
        console.log('Updating video placeholder, video enabled:', this.isVideoEnabled);
        
        // Update video placeholder visibility in waiting room
        const waitingRoomVideo = document.getElementById('waitingRoomVideo');
        const waitingRoomVideoPlaceholder = document.getElementById('waitingRoomVideoPlaceholder');
        
        if (waitingRoomVideo && waitingRoomVideoPlaceholder) {
            if (this.isVideoEnabled) {
                waitingRoomVideo.style.display = 'block';
                waitingRoomVideoPlaceholder.style.display = 'none';
                console.log('Waiting room video visible, placeholder hidden');
            } else {
                waitingRoomVideo.style.display = 'none';
                waitingRoomVideoPlaceholder.style.display = 'flex';
                console.log('Waiting room video hidden, placeholder visible');
            }
        } else {
            console.warn('Waiting room video elements not found');
        }
        
        // Also update main video elements if they exist
        const localVideo = document.getElementById('localVideo');
        const localPlaceholder = document.getElementById('localVideoPlaceholder');
        if (localVideo) {
            if (this.isVideoEnabled) {
                localVideo.classList.remove('hidden');
                if (localPlaceholder) localPlaceholder.classList.add('hidden');
                // reset any visual dimming
                localVideo.style.opacity = '1';
                localVideo.style.filter = 'none';
            } else {
                localVideo.classList.add('hidden');
                if (localPlaceholder) localPlaceholder.classList.remove('hidden');
            }
            console.log('Local video placeholder updated:', this.isVideoEnabled ? 'video' : 'placeholder');
        }
    }
    
    updateScreenShareButton() {
        const screenShareBtn = document.getElementById('screenShareToggle');
        if (screenShareBtn) {
            const icon = screenShareBtn.querySelector('i');
            
            if (this.isScreenSharing) {
                if (icon) icon.className = 'fas fa-stop text-white';
                screenShareBtn.className = 'w-12 h-12 bg-red-500 hover:bg-red-600 rounded-full flex items-center justify-center transition-all duration-300 hover:scale-110';
            } else {
                if (icon) icon.className = 'fas fa-desktop text-white';
                screenShareBtn.className = 'w-12 h-12 bg-blue-500 hover:bg-blue-600 rounded-full flex items-center justify-center transition-all duration-300 hover:scale-110';
            }
        }
    }
    
    updateRecordingButtons() {
        const recordBtn = document.getElementById('recordButton');
        const recordIndicator = document.getElementById('recordingIndicator');
        
        if (recordBtn) {
            const icon = recordBtn.querySelector('i');
            const text = recordBtn.querySelector('span');
            
            if (this.isRecording) {
                if (icon) icon.className = 'fas fa-stop mr-2 group-hover:animate-spin transition-transform duration-300';
                if (text) text.textContent = 'Stop';
                recordBtn.className = 'group flex items-center px-6 py-3 bg-gradient-to-r from-red-500 to-red-600 rounded-xl hover:from-red-600 hover:to-red-700 transition-all duration-300 text-white font-medium shadow-lg hover:shadow-xl transform hover:scale-105';
            } else {
                if (icon) icon.className = 'fas fa-record-vinyl mr-2 group-hover:animate-spin transition-transform duration-300';
                if (text) text.textContent = 'Record';
                recordBtn.className = 'group flex items-center px-6 py-3 bg-gradient-to-r from-blue-500 to-blue-600 rounded-xl hover:from-blue-600 hover:to-blue-700 transition-all duration-300 text-white font-medium shadow-lg hover:shadow-xl transform hover:scale-105';
            }
        }
        
        if (recordIndicator) {
            if (this.isRecording) {
                recordIndicator.classList.remove('hidden');
            } else {
                recordIndicator.classList.add('hidden');
            }
        }
    }
    
    showWaitingRoom() {
        console.log('Showing waiting room');
        const waitingRoom = document.getElementById('waitingRoomUI');
        const callInterface = document.getElementById('callUI');
        
        if (waitingRoom) {
            waitingRoom.classList.remove('hidden');
            console.log('Waiting room shown');
        } else {
            console.warn('Waiting room element not found');
        }
        
        if (callInterface) {
            callInterface.classList.add('hidden');
        }
        
        this.updateWaitingRoomMessage('Connecting to session...');
        
        // Initialize waiting room button states
        this.updateWaitingRoomButtons();
        this.updateVideoPlaceholder();
        
        // Ensure video stream is attached to waiting room video
        this.attachStreamToWaitingRoom();
    }
    
    attachStreamToWaitingRoom() {
        if (this.localStream) {
            const waitingRoomVideo = document.getElementById('waitingRoomVideo');
            if (waitingRoomVideo) {
                console.log('Attaching stream to waiting room video');
                waitingRoomVideo.srcObject = this.localStream;
                waitingRoomVideo.muted = true;
                
                // Ensure video plays
                waitingRoomVideo.onloadedmetadata = () => {
                    waitingRoomVideo.play().catch(e => {
                        console.warn('Error playing waiting room video:', e);
                    });
                };
                
                // Force play if metadata is already loaded
                if (waitingRoomVideo.readyState >= 2) {
                    waitingRoomVideo.play().catch(e => {
                        console.warn('Error playing waiting room video:', e);
                    });
                }
            } else {
                console.warn('Waiting room video element not found');
            }
        } else {
            console.warn('No local stream available for waiting room');
        }
    }
    
    updateWaitingRoomMessage(message) {
        const messageElement = document.getElementById('waitingRoomMessage');
        if (messageElement) {
            messageElement.textContent = message;
        }
    }
    
    showStartCallButton() {
        const startCallBtn = document.getElementById('startCallBtn');
        if (startCallBtn) {
            startCallBtn.classList.remove('hidden');
            startCallBtn.disabled = false;
        }
        // Update waiting room prompt for clarity
        this.updateWaitingRoomMessage('Both ready. Click "Start Video Call" to begin.');
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
        
        // Populate final notes field with current notes
        const finalNotesTextarea = document.getElementById('finalNotes');
        if (finalNotesTextarea) {
            finalNotesTextarea.value = this.sessionNotes;
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
        
        // Get final notes
        const finalNotesTextarea = document.getElementById('finalNotes');
        const finalNotes = finalNotesTextarea ? finalNotesTextarea.value : this.sessionNotes;
        
        this.socket.emit('end_session', {
            session_id: this.sessionId,
            final_notes: finalNotes
        });
        
        this.cleanup();
        this.hideEndSessionModal();
        
        // Redirect to session completion page
        setTimeout(() => {
            window.location.href = `/office/session-completed/${this.sessionId}`;
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
            window.location.href = `/office/session-completed/${this.sessionId}`;
        }, 3000);
    }
    
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
        
        // Update button icon/title to reflect fullscreen UI state
        const fullscreenBtn = document.getElementById('fullScreenToggle');
        if (fullscreenBtn) {
            const icon = fullscreenBtn.querySelector('i');
            if (icon) {
                icon.className = 'fas fa-compress text-white';
                fullscreenBtn.title = 'Exit Fullscreen';
            }
        }

        // Add fullscreen info overlay
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
                <i class="fas fa-expand text-green-400"></i>
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
            console.log(`Tab content ${index}:`, content.getAttribute('data-tab'), content.classList.toString());
            if (index === 0) {
                // Show first tab
                content.classList.remove('hidden');
                content.classList.add('active');
                content.style.display = 'block';
            }
        });
        
        // Activate first tab button
        const firstButton = document.querySelector('.tab-button');
        if (firstButton) {
            firstButton.classList.add('active');
            console.log('First tab button activated');
        }
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    // Get session data from page
    const sessionData = window.sessionData || {};
    
    if (sessionData.sessionId && sessionData.userId) {
        console.log('Initializing video counseling for session:', sessionData.sessionId);
        window.videoCounselingClient = new VideoCounselingClientOffice(
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