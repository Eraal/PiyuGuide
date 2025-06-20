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
            console.log('Initializing Video Counseling Client for Office...');
            this.updateConnectionStatus('Initializing...', 'info');
            this.initializeSocket();
            this.setupEventListeners();
            await this.initializeMedia();
            this.showWaitingRoom();
            // Initialize participant indicators - counselor is connected, student is not yet
            this.updateParticipantIndicators(true, false);
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
            }
        });
        
        this.socket.on('session_ready', (data) => {
            console.log('Session is ready to start:', data);
            this.showStartCallButton();
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
    
    async initializeMedia() {
        console.log('Requesting media access...');
        
        try {
            // Request permission for camera and microphone
            this.localStream = await navigator.mediaDevices.getUserMedia(this.mediaConstraints);
            console.log('Media access granted');
            
            // Attach to local video element
            const localVideo = document.getElementById('localVideo');
            if (localVideo) {
                localVideo.srcObject = this.localStream;
                localVideo.muted = true; // Prevent feedback
            }
            
            // Populate device lists
            await this.populateDeviceList();
            
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
        // Media control buttons
        const toggleAudioBtn = document.getElementById('toggleAudioBtn');
        if (toggleAudioBtn) {
            toggleAudioBtn.addEventListener('click', () => this.toggleAudio());
        }
        
        const toggleVideoBtn = document.getElementById('toggleVideoBtn');
        if (toggleVideoBtn) {
            toggleVideoBtn.addEventListener('click', () => this.toggleVideo());
        }
        
        // Screen sharing
        const screenShareBtn = document.getElementById('screenShareBtn');
        if (screenShareBtn) {
            screenShareBtn.addEventListener('click', () => this.toggleScreenShare());
        }
        
        // Recording controls
        const startRecordingBtn = document.getElementById('startRecordingBtn');
        if (startRecordingBtn) {
            startRecordingBtn.addEventListener('click', () => this.startRecording());
        }
        
        const stopRecordingBtn = document.getElementById('stopRecordingBtn');
        if (stopRecordingBtn) {
            stopRecordingBtn.addEventListener('click', () => this.stopRecording());
        }
        
        // End call button
        const endCallBtn = document.getElementById('endCallBtn');
        if (endCallBtn) {
            endCallBtn.addEventListener('click', () => this.showEndSessionModal());
        }
        
        // Start call button
        const startCallBtn = document.getElementById('startCallBtn');
        if (startCallBtn) {
            startCallBtn.addEventListener('click', () => this.startCall());
        }
        
        // Fullscreen button
        const fullscreenBtn = document.getElementById('fullscreenBtn');
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
                const tabName = e.target.dataset.tab;
                if (tabName) this.switchTab(tabName);
            });
        });
        
        // Notes functionality
        const notesTextarea = document.getElementById('sessionNotes');
        if (notesTextarea) {
            notesTextarea.addEventListener('input', (e) => {
                this.sessionNotes = e.target.value;
            });
        }
        
        const saveNotesBtn = document.getElementById('saveNotesBtn');
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
        console.log('Starting video call as counselor...');
        
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
            
            this.updateConnectionStatus('Call started - waiting for student response', 'info');
            
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
            console.log('Received remote stream');
            this.remoteStream = event.streams[0];
            const remoteVideo = document.getElementById('remoteVideo');
            if (remoteVideo) {
                remoteVideo.srcObject = this.remoteStream;
            }
            
            // Show call UI when we receive remote stream
            if (this.isInCall && !document.getElementById('callInterface').classList.contains('hidden')) {
                // UI already shown
            } else {
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
            
            // Check if we should show the call UI
            setTimeout(() => {
                if (this.isInCall && this.peerConnection.connectionState === 'connected') {
                    this.showCallUI();
                }
            }, 1000);
        }
    }
    
    showCallUI() {
        console.log('Showing call UI');
        const waitingRoom = document.getElementById('waitingRoom');
        const callInterface = document.getElementById('callInterface');
        
        if (waitingRoom) waitingRoom.classList.add('hidden');
        if (callInterface) callInterface.classList.remove('hidden');
        
        // Switch to video tab
        this.switchTab('video');
        
        // Update status
        this.updateConnectionStatus('Video call active', 'success');
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
            console.log('Starting screen share...');
            
            // Get screen capture stream
            this.screenShareStream = await navigator.mediaDevices.getDisplayMedia({
                video: true,
                audio: true
            });
            
            // Replace video track in peer connection
            if (this.peerConnection) {
                const videoSender = this.peerConnection.getSenders().find(sender => 
                    sender.track && sender.track.kind === 'video'
                );
                
                if (videoSender) {
                    await videoSender.replaceTrack(this.screenShareStream.getVideoTracks()[0]);
                }
            }
            
            // Update local video to show screen share
            const localVideo = document.getElementById('localVideo');
            if (localVideo) {
                localVideo.srcObject = this.screenShareStream;
            }
            
            this.isScreenSharing = true;
            this.updateScreenShareButton();
            
            // Handle when user stops sharing via browser controls
            this.screenShareStream.getVideoTracks()[0].onended = () => {
                this.stopScreenShare();
            };
            
            // Notify other participants
            this.socket.emit('screen_share_start', {
                session_id: this.sessionId
            });
            
            this.showNotification('Screen sharing started', 'success');
            
        } catch (error) {
            console.error('Error starting screen share:', error);
            this.showError('Failed to start screen sharing');
        }
    }
    
    async stopScreenShare() {
        try {
            console.log('Stopping screen share...');
            
            if (this.screenShareStream) {
                this.screenShareStream.getTracks().forEach(track => track.stop());
                this.screenShareStream = null;
            }
            
            // Replace with camera stream
            if (this.peerConnection && this.localStream) {
                const videoSender = this.peerConnection.getSenders().find(sender => 
                    sender.track && sender.track.kind === 'video'
                );
                
                if (videoSender) {
                    const cameraTrack = this.localStream.getVideoTracks()[0];
                    if (cameraTrack) {
                        await videoSender.replaceTrack(cameraTrack);
                    }
                }
            }
            
            // Update local video to show camera
            const localVideo = document.getElementById('localVideo');
            if (localVideo && this.localStream) {
                localVideo.srcObject = this.localStream;
            }
            
            this.isScreenSharing = false;
            this.updateScreenShareButton();
            
            // Notify other participants
            this.socket.emit('screen_share_stop', {
                session_id: this.sessionId
            });
            
            this.showNotification('Screen sharing stopped', 'info');
            
        } catch (error) {
            console.error('Error stopping screen share:', error);
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
        const audioBtn = document.getElementById('toggleAudioBtn');
        const videoBtn = document.getElementById('toggleVideoBtn');
        
        if (audioBtn) {
            const icon = audioBtn.querySelector('i');
            if (icon) {
                icon.className = this.isAudioEnabled ? 'fas fa-microphone' : 'fas fa-microphone-slash';
            }
            audioBtn.className = this.isAudioEnabled ? 
                'btn-enhanced bg-green-500 hover:bg-green-600 text-white' : 
                'btn-enhanced bg-red-500 hover:bg-red-600 text-white';
        }
        
        if (videoBtn) {
            const icon = videoBtn.querySelector('i');
            if (icon) {
                icon.className = this.isVideoEnabled ? 'fas fa-video' : 'fas fa-video-slash';
            }
            videoBtn.className = this.isVideoEnabled ? 
                'btn-enhanced bg-green-500 hover:bg-green-600 text-white' : 
                'btn-enhanced bg-red-500 hover:bg-red-600 text-white';
        }
    }
    
    updateScreenShareButton() {
        const screenShareBtn = document.getElementById('screenShareBtn');
        if (screenShareBtn) {
            const icon = screenShareBtn.querySelector('i');
            const text = screenShareBtn.querySelector('span');
            
            if (this.isScreenSharing) {
                if (icon) icon.className = 'fas fa-stop';
                if (text) text.textContent = 'Stop Sharing';
                screenShareBtn.className = 'btn-enhanced bg-red-500 hover:bg-red-600 text-white';
            } else {
                if (icon) icon.className = 'fas fa-desktop';
                if (text) text.textContent = 'Share Screen';
                screenShareBtn.className = 'btn-enhanced bg-blue-500 hover:bg-blue-600 text-white';
            }
        }
    }
    
    updateRecordingButtons() {
        const startBtn = document.getElementById('startRecordingBtn');
        const stopBtn = document.getElementById('stopRecordingBtn');
        
        if (startBtn && stopBtn) {
            if (this.isRecording) {
                startBtn.classList.add('hidden');
                stopBtn.classList.remove('hidden');
            } else {
                startBtn.classList.remove('hidden');
                stopBtn.classList.add('hidden');
            }
        }
    }
    
    showWaitingRoom() {
        const waitingRoom = document.getElementById('waitingRoom');
        const callInterface = document.getElementById('callInterface');
        
        if (waitingRoom) waitingRoom.classList.remove('hidden');
        if (callInterface) callInterface.classList.add('hidden');
        
        this.updateWaitingRoomMessage('Connecting to session...');
    }
    
    showCallUI() {
        console.log('Showing call UI');
        const waitingRoom = document.getElementById('waitingRoom');
        const callInterface = document.getElementById('callInterface');
        
        if (waitingRoom) waitingRoom.classList.add('hidden');
        if (callInterface) callInterface.classList.remove('hidden');
        
        // Switch to video tab
        this.switchTab('video');
        
        // Update status
        this.updateConnectionStatus('Video call active', 'success');
    }
    
    updateWaitingRoomMessage(message) {
        const messageElement = document.getElementById('waitingMessage');
        if (messageElement) {
            messageElement.textContent = message;
        }
    }
    
    updateConnectionStatus(status, type = 'info') {
        const statusElement = document.getElementById('connectionStatus');
        if (statusElement) {
            statusElement.textContent = status;
            
            // Update status styling
            statusElement.className = 'text-sm font-medium';
            switch (type) {
                case 'success':
                    statusElement.classList.add('text-green-600');
                    break;
                case 'warning':
                    statusElement.classList.add('text-yellow-600');
                    break;
                case 'error':
                    statusElement.classList.add('text-red-600');
                    break;
                default:
                    statusElement.classList.add('text-blue-600');
            }
        }
        
        // Also update any connection indicators
        this.updateConnectionIndicators(type, type === 'success');
    }
    
    startSessionTimer() {
        this.startTime = new Date();
        this.sessionTimer = setInterval(() => {
            const elapsed = new Date() - this.startTime;
            const minutes = Math.floor(elapsed / 60000);
            const seconds = Math.floor((elapsed % 60000) / 1000);
            
            const timerElement = document.getElementById('sessionTimer');
            if (timerElement) {
                timerElement.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
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
        
        // Redirect to session summary or dashboard
        setTimeout(() => {
            window.location.href = '/office/counseling-sessions';
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
            window.location.href = '/office/counseling-sessions';
        }, 3000);
    }
    
    cleanup() {
        console.log('Cleaning up video counseling session...');
        
        this.stopSessionTimer();
        this.stopHeartbeat();
        
        // Stop screen sharing if active
        if (this.isScreenSharing) {
            this.stopScreenShare();
        }
        
        // Stop recording if active
        if (this.isRecording) {
            this.stopRecording();
        }
        
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
        // Hide all tab contents
        const tabContents = document.querySelectorAll('.tab-content');
        tabContents.forEach(content => content.classList.add('hidden'));
        
        // Remove active class from all buttons
        const tabButtons = document.querySelectorAll('.tab-button');
        tabButtons.forEach(button => button.classList.remove('active'));
        
        // Show selected tab content
        const selectedContent = document.getElementById(`${tabName}Tab`);
        if (selectedContent) {
            selectedContent.classList.remove('hidden');
        }
        
        // Add active class to selected button
        const selectedButton = document.querySelector(`[data-tab="${tabName}"]`);
        if (selectedButton) {
            selectedButton.classList.add('active');
        }
    }
    
    toggleFullScreen() {
        const remoteVideo = document.getElementById('remoteVideo');
        if (remoteVideo) {
            if (document.fullscreenElement) {
                document.exitFullscreen();
            } else {
                remoteVideo.requestFullscreen().catch(err => {
                    console.error('Error attempting to enable fullscreen:', err);
                });
            }
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
    
    updateParticipantIndicators(counselorPresent = true, studentPresent = false) {
        // Update counselor indicator (should always be green for current user)
        const counselorIndicator = document.getElementById('counselorIndicator');
        const counselorStatus = counselorIndicator?.parentElement?.nextElementSibling;
        
        if (counselorIndicator) {
            counselorIndicator.className = 'w-4 h-4 rounded-full bg-emerald-500';
            
            // Update the ping animation div
            const pingDiv = counselorIndicator.nextElementSibling;
            if (pingDiv) {
                pingDiv.className = 'absolute inset-0 rounded-full bg-emerald-500 animate-ping opacity-75';
            }
        }
        
        if (counselorStatus) {
            counselorStatus.textContent = 'You (Ready)';
            counselorStatus.className = 'text-sm font-medium text-emerald-600';
        }
        
        // Update student indicator
        const studentIndicator = document.getElementById('studentIndicator');
        const studentStatus = studentIndicator?.parentElement?.nextElementSibling;
        
        if (studentIndicator) {
            studentIndicator.className = studentPresent ? 
                'w-4 h-4 rounded-full bg-emerald-500' : 
                'w-4 h-4 rounded-full bg-slate-300';
                
            // Update the ping animation div
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
    
    showStartCallButton() {
        const startCallBtn = document.getElementById('startCallBtn');
        if (startCallBtn) {
            startCallBtn.classList.remove('hidden');
            startCallBtn.disabled = false;
        }
        
        this.updateWaitingRoomMessage('Ready to start! Click "Start Call" to begin.');
    }
    
    handleRemoteAudioToggle(data) {
        console.log(`${data.name} ${data.audio_enabled ? 'enabled' : 'disabled'} their microphone`);
        // Could update UI to show remote user's audio state
    }
    
    handleRemoteVideoToggle(data) {
        console.log(`${data.name} ${data.video_enabled ? 'enabled' : 'disabled'} their camera`);
        // Could update UI to show remote user's video state
    }
    
    handleStudentDisconnect() {
        this.showNotification('Student has left the session', 'warning');
        this.updateConnectionStatus('Waiting for student to return...', 'warning');
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